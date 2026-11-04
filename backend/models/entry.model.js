const mongoose = require('mongoose');

const entrySchema = new mongoose.Schema({
    user: {
        type: mongoose.Schema.Types.ObjectId,
        ref: 'User',
        required: true,
    },
    text: {
        type: String,
        default: '',
    },
    text1: {
        type: String,
        default: '',
    },
    text2: {
        type: String,
        default: '',
    },
    text3: {
        type: String,
        default: '',
    },
    image: {
        type: String,
        default: '',
    },
    audio: {
        type: String,
        default: '',
    },
    audioText: {
        type: String,
        default: '',
    },
    location: {
        lat: { type: Number },
        lng: { type: Number },
    },
    similarityReport: {
        type: mongoose.Schema.Types.Mixed,
        default: null
    },
    disasterReport: {
        type: mongoose.Schema.Types.Mixed,
        default: null
    },
    ragReport: {
        type: mongoose.Schema.Types.Mixed,
        default: null
    },
    resourceEngineReport: {
        type: mongoose.Schema.Types.Mixed,
        default: null
    },
    intakeRecord: {
        type: mongoose.Schema.Types.Mixed,
        default: null
    },
    conversationId: {
        type: String,
        index: true,
        default: null
    },
    conversationTitle: {
        type: String,
        default: ''
    },
    status: {
        type: String,
        enum: ['DRAFT', 'NEEDS_CLARIFICATION', 'READY_FOR_ASSESSMENT', 'ORCHESTRATING', 'MISSION_ACTIVE'],
        default: 'READY_FOR_ASSESSMENT'
    },
    imageCaption: {
        type: String,
        default: ''
    },
    clientTimestamp: {
        type: Date,
    },
    isDevTest: {
        type: Boolean,
        default: false,
        index: true
    },
    deletedByUser: {
        type: Boolean,
        default: false,
        index: true
    }
}, { timestamps: true });

module.exports = mongoose.model('Entry', entrySchema);
