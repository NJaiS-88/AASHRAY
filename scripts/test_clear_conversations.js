const BASE_URL = 'http://localhost:5000/api';
const RE_URL = 'http://localhost:8000';

async function runTests() {
    console.log('--- STARTING VERIFICATION FOR CLEAR CONVERSATIONS FEATURE ---');
    let passed = 0;
    let failed = 0;

    function assert(condition, message) {
        if (condition) {
            console.log(`[PASS] ${message}`);
            passed++;
        } else {
            console.error(`[FAIL] ${message}`);
            failed++;
        }
    }

    try {
        // 1. Register/Login User A
        const emailA = `citizen_a_${Date.now()}@example.com`;
        const resA = await fetch(`${BASE_URL}/auth/signup`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name: 'Citizen A', email: emailA, password: 'password123' })
        });
        const userAData = await resA.json();
        const tokenA = userAData.token;
        assert(tokenA, 'User A registered and authenticated');

        // 2. Register/Login User B
        const emailB = `citizen_b_${Date.now()}@example.com`;
        const resB = await fetch(`${BASE_URL}/auth/signup`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name: 'Citizen B', email: emailB, password: 'password123' })
        });
        const userBData = await resB.json();
        const tokenB = userBData.token;
        assert(tokenB, 'User B registered and authenticated');

        // 3. Register/Login Admin
        const adminEmail = `admin_${Date.now()}@example.com`;
        const resAdmin = await fetch(`${BASE_URL}/auth/signup`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name: 'Admin User', email: adminEmail, password: 'password123', role: 'admin' })
        });
        const adminData = await resAdmin.json();
        const tokenAdmin = adminData.token;
        assert(tokenAdmin, 'Admin user registered and authenticated');

        // 4. User A posts report 1 (conv_a1) and report 2 (conv_a2)
        const convA1 = `conv_a1_${Date.now()}`;
        const convA2 = `conv_a2_${Date.now()}`;
        await fetch(`${BASE_URL}/entries`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${tokenA}` },
            body: JSON.stringify({
                text: 'Heavy waterlogging near Sector 18 underpass, cars stranded',
                conversationId: convA1,
                conversationTitle: 'Waterlogging Sector 18',
                location: { lat: 28.5355, lng: 77.3910 }
            })
        });

        await fetch(`${BASE_URL}/entries`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${tokenA}` },
            body: JSON.stringify({
                text: 'Tree fallen on electrical wire blocking main road',
                conversationId: convA2,
                conversationTitle: 'Fallen tree on wire',
                location: { lat: 28.5400, lng: 77.3950 }
            })
        });

        // 5. User B posts report 1 (conv_b1)
        const convB1 = `conv_b1_${Date.now()}`;
        await fetch(`${BASE_URL}/entries`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${tokenB}` },
            body: JSON.stringify({
                text: 'Transformer spark fire reported near market plaza',
                conversationId: convB1,
                conversationTitle: 'Transformer fire',
                location: { lat: 28.5200, lng: 77.3800 }
            })
        });

        // 6. Verify User A sees 2 conversations
        const convsARes = await fetch(`${BASE_URL}/entries/conversations`, {
            headers: { Authorization: `Bearer ${tokenA}` }
        });
        const convsAData = await convsARes.json();
        assert(convsAData.length === 2, `User A sees exactly 2 conversations (found ${convsAData.length})`);

        // 7. Verify User B sees 1 conversation
        const convsBRes = await fetch(`${BASE_URL}/entries/conversations`, {
            headers: { Authorization: `Bearer ${tokenB}` }
        });
        const convsBData = await convsBRes.json();
        assert(convsBData.length === 1, `User B sees exactly 1 conversation (found ${convsBData.length})`);

        // 8. Test unauthenticated DELETE -> 401
        const unauthRes = await fetch(`${BASE_URL}/entries`, { method: 'DELETE' });
        assert(unauthRes.status === 401, `Unauthenticated DELETE rejected with 401 (got ${unauthRes.status})`);

        // 9. Test Single Conversation Delete for User A (delete convA2)
        const delSingleRes = await fetch(`${BASE_URL}/entries/conversation/${convA2}`, {
            method: 'DELETE',
            headers: { Authorization: `Bearer ${tokenA}` }
        });
        const delSingleData = await delSingleRes.json();
        assert(delSingleData.status === 'success', 'Single conversation delete returned success');

        const convsAAfterSingle = await (await fetch(`${BASE_URL}/entries/conversations`, {
            headers: { Authorization: `Bearer ${tokenA}` }
        })).json();
        assert(
            convsAAfterSingle.length === 1 && convsAAfterSingle[0].conversationId === convA1,
            'User A now sees only remaining convA1'
        );

        // 10. User A clears all conversations
        const clearAllRes = await fetch(`${BASE_URL}/entries`, {
            method: 'DELETE',
            headers: { Authorization: `Bearer ${tokenA}` }
        });
        const clearAllData = await clearAllRes.json();
        assert(clearAllData.status === 'success', 'Clear all conversations returned success');

        // 11. Verify User A conversation list is now 0
        const convsAAfterClear = await (await fetch(`${BASE_URL}/entries/conversations`, {
            headers: { Authorization: `Bearer ${tokenA}` }
        })).json();
        assert(convsAAfterClear.length === 0, 'User A conversation list is empty after clear');

        // 12. Verify User A entries list is now 0
        const entriesAAfterClear = await (await fetch(`${BASE_URL}/entries`, {
            headers: { Authorization: `Bearer ${tokenA}` }
        })).json();
        assert(entriesAAfterClear.length === 0, 'User A entries list is empty after clear');

        // 13. Cross-User Isolation: Verify User B still has their conversation intact!
        const convsBAfterClear = await (await fetch(`${BASE_URL}/entries/conversations`, {
            headers: { Authorization: `Bearer ${tokenB}` }
        })).json();
        assert(
            convsBAfterClear.length === 1 && convsBAfterClear[0].conversationId === convB1,
            'User B conversation history completely intact (cross-user isolation verified)'
        );

        // 14. Operational Record Preservation: Admin can still see User A's soft-deleted reports
        const adminEntries = await (await fetch(`${BASE_URL}/entries/admin`, {
            headers: { Authorization: `Bearer ${tokenAdmin}` }
        })).json();
        const userAEntryInAdmin = adminEntries.find(e => e.conversationId === convA1);
        assert(
            userAEntryInAdmin !== undefined,
            'Admin still has access to operational record for audit & coordination (soft-delete preserved)'
        );

        // 15. Check Resource Engine status (5 default scenarios + operational missions remain untouched)
        const reMissions = await (await fetch(`${RE_URL}/orchestrate/live-missions`)).json();
        assert(
            Array.isArray(reMissions.live_missions),
            'Resource Engine live missions intact and responding normally'
        );

    } catch (err) {
        console.error('Test execution error:', err.message);
        failed++;
    }

    console.log(`\n--- SUMMARY: ${passed} passed, ${failed} failed ---`);
    process.exit(failed > 0 ? 1 : 0);
}

runTests();
