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
    clientTimestamp: {
        type: Date,
    }
}, { timestamps: true });

module.exports = mongoose.model('Entry', entrySchema);
