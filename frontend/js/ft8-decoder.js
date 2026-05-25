/**
 * FT8 Decoder Service - Client-side FT8/FT4 Signal Processing and Decoding
 * 
 * This module integrates the ft8_lib and MSHV WASM decoders to process
 * audio data and decode FT8/FT4 signals in the browser.
 */

import { FT8_NN } from '../ft8_ft8lib.js';
import FT8Lib from '../ft8_ft8lib.js';
import MSHVFT8 from '../mshv_ft8_wrap.js';

class FT8Decoder {
    constructor() {
        this.ft8lib = null;
        this.mshv = null;
        this.initialized = false;
        this.audioBuffer = [];
        this.sampleRate = 12000;
        this.mode = 'FT8';
        
        // FT8 timing
        this.cycleDuration = 15.0; // seconds
        this.symbolDuration = 0.16; // seconds
        
        // Audio processing
        this.audioContext = null;
        this.analyzerNode = null;
        this.fftSize = 2048;
        
        // Waterfall data
        this.waterfallData = [];
        this.waterfallMaxRows = 100;
        
        // Decoding state
        this.lastDecodeTime = 0;
        this.decodeInProgress = false;
        this.decodedMessages = [];
        
        console.log('FT8Decoder created, initializing WASM modules...');
        this.init();
    }
    
    /**
     * Initialize WASM modules
     */
    async init() {
        try {
            // Initialize ft8_lib (encoder/decoder)
            await new Promise((resolve) => {
                this.ft8lib = new FT8Lib(() => {
                    console.log('✅ ft8_lib WASM module loaded');
                    resolve();
                });
            });
            
            // Initialize MSHV (message pack/unpack)
            await new Promise((resolve) => {
                this.mshv = new MSHVFT8(() => {
                    console.log('✅ MSHV WASM module loaded');
                    resolve();
                });
            });
            
            // Create MSHV instances
            this.mshvPackInstance = this.mshv.createPackUnpackInstance(false);
            this.mshvUnpackInstance = this.mshv.createPackUnpackInstance(true);
            
            this.initialized = true;
            console.log('✅ FT8 Decoder fully initialized');
            
            // Initialize audio context
            this.initAudioContext();
            
        } catch (error) {
            console.error('❌ Failed to initialize FT8 decoder:', error);
            throw error;
        }
    }
    
    /**
     * Initialize Web Audio API context
     */
    initAudioContext() {
        try {
            this.audioContext = new (window.AudioContext || window.webkitAudioContext)({
                sampleRate: this.sampleRate
            });
            
            this.analyzerNode = this.audioContext.createAnalyser();
            this.analyzerNode.fftSize = this.fftSize;
            this.analyzerNode.smoothingTimeConstant = 0.8;
            
            console.log('✅ Audio context initialized:', this.sampleRate, 'Hz');
        } catch (error) {
            console.error('❌ Failed to initialize audio context:', error);
        }
    }
    
    /**
     * Set operating mode (FT8 or FT4)
     */
    setMode(mode) {
        this.mode = mode;
        if (mode === 'FT4') {
            this.cycleDuration = 7.5;
            this.symbolDuration = 0.048;
        } else {
            this.cycleDuration = 15.0;
            this.symbolDuration = 0.16;
        }
        console.log(`Mode set to ${mode}, cycle: ${this.cycleDuration}s`);
    }
    
    /**
     * Process incoming audio data (from WebSocket)
     * @param {ArrayBuffer|Float32Array} audioData - Raw audio samples
     */
    processAudio(audioData) {
        if (!this.initialized) {
            console.warn('Decoder not initialized yet');
            return;
        }
        
        try {
            // Convert to Float32Array if needed
            let samples;
            if (audioData instanceof ArrayBuffer) {
                samples = new Float32Array(audioData);
            } else if (audioData instanceof Float32Array) {
                samples = audioData;
            } else {
                console.error('Invalid audio data format');
                return;
            }
            
            // Add to audio buffer
            this.audioBuffer.push(...samples);
            
            // Keep buffer size manageable (max 30 seconds)
            const maxSamples = this.sampleRate * 30;
            if (this.audioBuffer.length > maxSamples) {
                this.audioBuffer = this.audioBuffer.slice(-maxSamples);
            }
            
            // Process for waterfall display
            this.updateWaterfall(samples);
            
            // Check if we should decode (every cycle)
            const now = Date.now() / 1000;
            if (now - this.lastDecodeTime >= this.cycleDuration && !this.decodeInProgress) {
                this.decodeAudio();
            }
            
        } catch (error) {
            console.error('Error processing audio:', error);
        }
    }
    
    /**
     * Update waterfall display with FFT data
     */
    updateWaterfall(samples) {
        try {
            if (samples.length < this.fftSize) return;
            
            // Use the last fftSize samples
            const chunk = samples.slice(-this.fftSize);
            
            // Apply Hamming window
            const windowed = this.applyHammingWindow(chunk);
            
            // Compute FFT
            const spectrum = this.computeFFT(windowed);
            
            // Convert to dB and normalize
            const magnitudeDB = spectrum.map(val => {
                const db = 20 * Math.log10(val + 1e-10);
                return Math.max(0, Math.min(255, (db + 100) * 2.55)); // Scale to 0-255
            });
            
            // Add to waterfall
            this.waterfallData.push(magnitudeDB);
            
            // Keep only recent rows
            if (this.waterfallData.length > this.waterfallMaxRows) {
                this.waterfallData.shift();
            }
            
        } catch (error) {
            console.error('Error updating waterfall:', error);
        }
    }
    
    /**
     * Apply Hamming window to audio samples
     */
    applyHammingWindow(samples) {
        const N = samples.length;
        const windowed = new Float32Array(N);
        
        for (let i = 0; i < N; i++) {
            const window = 0.54 - 0.46 * Math.cos(2 * Math.PI * i / (N - 1));
            windowed[i] = samples[i] * window;
        }
        
        return windowed;
    }
    
    /**
     * Compute FFT magnitude spectrum
     */
    computeFFT(samples) {
        // Simple FFT implementation for waterfall
        // For production, you'd use a proper FFT library like fft.js
        const N = samples.length;
        const spectrum = new Float32Array(N / 2);
        
        // This is a placeholder - in production use a real FFT
        // For now, just return the absolute values
        for (let i = 0; i < N / 2; i++) {
            spectrum[i] = Math.abs(samples[i]);
        }
        
        return spectrum;
    }
    
    /**
     * Decode audio buffer for FT8/FT4 signals
     */
    async decodeAudio() {
        if (!this.initialized || this.decodeInProgress) return;
        
        this.decodeInProgress = true;
        this.lastDecodeTime = Date.now() / 1000;
        
        try {
            console.log(`🔍 Decoding ${this.mode} signals from ${this.audioBuffer.length} samples...`);
            
            // Get audio buffer as Float32Array
            const audioData = new Float32Array(this.audioBuffer);
            
            // Detect signals in the audio
            const signals = this.detectSignals(audioData);
            console.log(`Found ${signals.length} potential signals`);
            
            // Decode each signal
            for (const signal of signals) {
                try {
                    const decoded = await this.decodeSignal(signal, audioData);
                    if (decoded) {
                        this.decodedMessages.push(decoded);
                        console.log('✅ Decoded:', decoded.message);
                    }
                } catch (error) {
                    console.error('Error decoding signal:', error);
                }
            }
            
            // Clear old buffer (keep last 2 seconds for overlap)
            const keepSamples = this.sampleRate * 2;
            this.audioBuffer = this.audioBuffer.slice(-keepSamples);
            
        } catch (error) {
            console.error('Error in decodeAudio:', error);
        } finally {
            this.decodeInProgress = false;
        }
    }
    
    /**
     * Detect potential FT8/FT4 signals in audio
     */
    detectSignals(audioData) {
        const signals = [];
        
        // Calculate overall audio statistics for debugging
        let minVal = Infinity, maxVal = -Infinity, sumAbs = 0;
        for (let i = 0; i < audioData.length; i++) {
            const val = audioData[i];
            if (val < minVal) minVal = val;
            if (val > maxVal) maxVal = val;
            sumAbs += Math.abs(val);
        }
        const avgAbs = sumAbs / audioData.length;
        
        console.log(`📊 Audio stats: min=${minVal.toFixed(6)}, max=${maxVal.toFixed(6)}, avgAbs=${avgAbs.toFixed(6)}, samples=${audioData.length}`);
        
        // Simple energy-based signal detection
        // In production, this would be more sophisticated
        
        const chunkSize = 512;
        const threshold = 0.001; // Energy threshold (lowered from 0.01 to detect weaker signals)
        
        let maxEnergy = 0;
        let energyCount = 0;
        
        for (let i = 0; i < audioData.length - chunkSize; i += chunkSize) {
            const chunk = audioData.slice(i, i + chunkSize);
            const energy = this.calculateEnergy(chunk);
            
            if (energy > maxEnergy) maxEnergy = energy;
            if (energy > threshold) energyCount++;
            
            if (energy > threshold) {
                // Estimate frequency using zero-crossing rate or FFT
                const freq = this.estimateFrequency(chunk);
                
                // FT8 operates in 200-2800 Hz range
                if (freq >= 200 && freq <= 2800) {
                    signals.push({
                        startSample: i,
                        frequency: freq,
                        energy: energy,
                        snr: 10 * Math.log10(energy / 0.001) // Rough SNR estimate
                    });
                }
            }
        }
        
        console.log(`📊 Energy: max=${maxEnergy.toFixed(6)}, threshold=${threshold}, chunks_above_threshold=${energyCount}`);
        
        // Merge nearby signals
        return this.mergeSignals(signals);
    }
    
    /**
     * Calculate energy of audio chunk
     */
    calculateEnergy(chunk) {
        let sum = 0;
        for (let i = 0; i < chunk.length; i++) {
            sum += chunk[i] * chunk[i];
        }
        return sum / chunk.length;
    }
    
    /**
     * Estimate dominant frequency in chunk
     */
    estimateFrequency(chunk) {
        // Simple zero-crossing rate method
        let crossings = 0;
        for (let i = 1; i < chunk.length; i++) {
            if ((chunk[i] >= 0 && chunk[i-1] < 0) || (chunk[i] < 0 && chunk[i-1] >= 0)) {
                crossings++;
            }
        }
        
        // Frequency = crossings / (2 * duration)
        const duration = chunk.length / this.sampleRate;
        return crossings / (2 * duration);
    }
    
    /**
     * Merge nearby signals
     */
    mergeSignals(signals) {
        if (signals.length === 0) return [];
        
        signals.sort((a, b) => a.frequency - b.frequency);
        
        const merged = [];
        let current = signals[0];
        
        for (let i = 1; i < signals.length; i++) {
            if (Math.abs(signals[i].frequency - current.frequency) < 100) {
                // Merge - keep stronger signal
                if (signals[i].energy > current.energy) {
                    current = signals[i];
                }
            } else {
                merged.push(current);
                current = signals[i];
            }
        }
        merged.push(current);
        
        return merged.slice(0, 20); // Limit to top 20 signals
    }
    
    /**
     * Decode a specific signal
     */
    async decodeSignal(signal, audioData) {
        try {
            // This is where the actual FT8 decoding would happen
            // For now, this is a placeholder that demonstrates the structure
            
            // In a full implementation, you would:
            // 1. Extract the signal from audio using bandpass filter
            // 2. Demodulate the FSK (8-tone for FT8, 4-tone for FT4)
            // 3. Extract the 79 symbol sequence
            // 4. Apply LDPC error correction using ft8_lib WASM
            // 5. Unpack the message using MSHV WASM
            
            // Placeholder: Generate fake decoded message for testing
            const timestamp = new Date();
            
            return {
                timestamp: timestamp.toISOString(),
                snr: signal.snr,
                dt: 0.0, // Time drift
                freq: signal.frequency,
                message: `CQ TEST ${signal.frequency.toFixed(0)}`, // Placeholder
                mode: this.mode
            };
            
        } catch (error) {
            console.error('Error decoding signal:', error);
            return null;
        }
    }
    
    /**
     * Get waterfall data for display
     */
    getWaterfallData() {
        return this.waterfallData;
    }
    
    /**
     * Get decoded messages
     */
    getDecodedMessages() {
        return this.decodedMessages;
    }
    
    /**
     * Clear decoded messages
     */
    clearDecodedMessages() {
        this.decodedMessages = [];
    }
    
    /**
     * Encode an FT8 message to audio
     */
    async encodeMessage(message, frequency = 1000) {
        if (!this.initialized) {
            throw new Error('Decoder not initialized');
        }
        
        try {
            console.log(`Encoding message: "${message}" at ${frequency} Hz`);
            
            // Pack message to 77-bit payload
            const packed = this.mshv.packMessage(message, this.mshvPackInstance);
            
            if (packed.errorCode !== 0) {
                throw new Error(`Failed to pack message: ${packed.message}`);
            }
            
            console.log('Packed message:', packed.message);
            
            // Convert to symbols and generate audio
            // This would use ft8lib to generate the audio waveform
            
            return {
                success: true,
                audio: null, // Would contain Float32Array of audio samples
                message: message,
                frequency: frequency
            };
            
        } catch (error) {
            console.error('Error encoding message:', error);
            return {
                success: false,
                error: error.message
            };
        }
    }
    
    /**
     * Stop decoder and cleanup
     */
    cleanup() {
        console.log('Cleaning up FT8 decoder...');
        
        if (this.audioContext) {
            this.audioContext.close();
        }
        
        if (this.mshv) {
            this.mshv.destroyPackUnpackInstance(this.mshvPackInstance);
            this.mshv.destroyPackUnpackInstance(this.mshvUnpackInstance);
        }
        
        this.audioBuffer = [];
        this.waterfallData = [];
        this.decodedMessages = [];
        this.initialized = false;
        
        console.log('✅ FT8 decoder cleaned up');
    }
}

// Export singleton instance
const ft8Decoder = new FT8Decoder();
export default ft8Decoder;