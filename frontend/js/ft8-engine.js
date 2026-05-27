/**
 * Built-in FT8 engine boundary.
 *
 * This module deliberately exposes only capabilities that are backed by a real
 * engine path. It does not synthesize fake decodes.
 */

const DEFAULT_CAPABILITIES = Object.freeze({
    engine: 'ft8_lib',
    license: 'MIT',
    ready: false,
    mode: 'FT8',
    receive: 'unavailable',
    transmit: false,
    waterfall: true,
    messageEncode: true,
    audioGenerate: true
});

class FT8Engine {
    constructor() {
        this.mode = 'FT8';
        this.ft8lib = null;
        this.ready = false;
        this.initPromise = null;
    }

    async init() {
        if (this.ready) {
            return this;
        }

        if (!this.initPromise) {
            this.initPromise = this._loadFT8Lib();
        }

        await this.initPromise;
        return this;
    }

    async _loadFT8Lib() {
        const module = await import('../ft8_ft8lib.js');
        const FT8Lib = module.default;

        this.ft8lib = await new Promise((resolve, reject) => {
            try {
                const instance = new FT8Lib(() => resolve(instance));
            } catch (error) {
                reject(error);
            }
        });

        this.ready = true;
    }

    setMode(mode) {
        this.mode = mode === 'FT4' ? 'FT4' : 'FT8';
    }

    getCapabilities() {
        return {
            ...DEFAULT_CAPABILITIES,
            ready: this.ready,
            mode: this.mode
        };
    }

    async encodeMessage(message, options = {}) {
        await this.init();

        if (this.mode !== 'FT8') {
            throw new Error('The bundled ft8_lib path currently supports FT8 only');
        }

        const text = String(message || '').trim().toUpperCase();
        if (!text) {
            throw new Error('Message is required');
        }

        const packed = this.ft8lib.messageToPackedData(text);
        if (!packed.success) {
            throw new Error(packed.errorMessage || `FT8 encode failed (${packed.errorCode})`);
        }

        const symbols = this.ft8lib.packedDataToSymbols(packed.data);
        const baseFreq = Number(options.baseFreq || 1200);
        const sampleRate = Number(options.sampleRate || 12000);
        const audio = this.ft8lib.symbolsToAudio(symbols, baseFreq, sampleRate);

        return {
            message: text,
            packedBytes: packed.data.length,
            symbols,
            audioSampleCount: audio.audio.length,
            sampleRate,
            metadata: audio.metadata || ''
        };
    }

    processAudio() {
        return {
            success: false,
            decoded: [],
            reason: 'Client-side FT8 decode is unavailable; built-in receive uses the backend decoder path'
        };
    }

    decodeAudio() {
        return this.processAudio();
    }

    getDecodedMessages() {
        return [];
    }

    getWaterfallData() {
        return [];
    }

    clearDecodedMessages() {
        return undefined;
    }
}

export default new FT8Engine();
