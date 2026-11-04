with open('backend/routes/entries.js', 'r', encoding='utf-8') as f:
    content = f.read()

# 1. Update GET /conversations
t1 = """        const threads = await Entry.aggregate([
            { $match: { user: activeUser._id } },"""
r1 = """        const threads = await Entry.aggregate([
            { $match: { user: activeUser._id, deletedByUser: { $ne: true } } },"""

assert t1 in content, "t1 not found in entries.js"
content = content.replace(t1, r1, 1)

# 2. Update GET /
t2 = """// GET entries for current user (least-privilege serialized with thread support)
router.get('/', protect, async (req, res) => {
    try {
        const activeUser = req.user;
        const filter = activeUser?._id ? { user: activeUser._id } : {};"""

r2 = """// GET entries for current user (least-privilege serialized with thread support)
router.get('/', protect, async (req, res) => {
    try {
        const activeUser = req.user;
        const filter = activeUser?._id ? { user: activeUser._id, deletedByUser: { $ne: true } } : { deletedByUser: { $ne: true } };"""

assert t2 in content, "t2 not found in entries.js"
content = content.replace(t2, r2, 1)

# 3. Update DELETE / and add DELETE /conversation/:conversationId
t3 = """// DELETE all entries/chats for user
router.delete('/', protect, async (req, res) => {
    try {
        const activeUser = req.user;
        const filter = activeUser?._id ? { user: activeUser._id } : {};
        await Entry.deleteMany(filter);
        res.json({ message: 'All chat history cleared from backend' });
    } catch (error) {
        res.status(500).json({ message: error.message });
    }
});"""

r3 = """// DELETE all entries/chats for user (user-scoped soft-delete preserving operational dispatches)
router.delete('/', protect, async (req, res) => {
    try {
        const activeUser = req.user;
        if (!activeUser?._id) return res.status(401).json({ message: 'Unauthorized' });
        const result = await Entry.updateMany(
            { user: activeUser._id, deletedByUser: { $ne: true } },
            { $set: { deletedByUser: true } }
        );
        res.json({
            status: 'success',
            message: 'All conversations and chat history cleared for user',
            clearedCount: result.modifiedCount
        });
    } catch (error) {
        res.status(500).json({ message: error.message });
    }
});

// DELETE single conversation thread for user
router.delete('/conversation/:conversationId', protect, async (req, res) => {
    try {
        const activeUser = req.user;
        if (!activeUser?._id) return res.status(401).json({ message: 'Unauthorized' });
        const cId = req.params.conversationId;
        const query = { user: activeUser._id, deletedByUser: { $ne: true } };
        if (cId === 'default') {
            query.$or = [{ conversationId: 'default' }, { conversationId: null }, { conversationId: { $exists: false } }];
        } else {
            query.conversationId = cId;
        }
        const result = await Entry.updateMany(
            query,
            { $set: { deletedByUser: true } }
        );
        res.json({
            status: 'success',
            message: `Conversation ${cId} cleared for user`,
            clearedCount: result.modifiedCount
        });
    } catch (error) {
        res.status(500).json({ message: error.message });
    }
});"""

assert t3 in content, "t3 not found in entries.js"
content = content.replace(t3, r3, 1)

with open('backend/routes/entries.js', 'w', encoding='utf-8') as f:
    f.write(content)

print("Successfully updated backend/routes/entries.js")
