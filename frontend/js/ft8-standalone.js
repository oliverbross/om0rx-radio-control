// Standalone FT8/FT4 window entry point.

(async function bootstrapFT8Window() {
    const root = document.getElementById('ft8-window-root');
    const response = await fetch('templates/modal-ft8.html?v=20260527-compact1', {
        cache: 'no-store'
    });
    if (!response.ok) {
        throw new Error(`Failed to load FT8 template: HTTP ${response.status}`);
    }
    root.innerHTML = await response.text();

    const { createApp } = Vue;
    const app = createApp({
        data() {
            return {
                ...(window.ft8ModalMixin ? window.ft8ModalMixin.data() : {})
            };
        },
        methods: {
            ...(window.ft8ModalMixin ? window.ft8ModalMixin.methods : {})
        },
        mounted() {
            this.openFT8Modal();
        },
        beforeUnmount() {
            if (this.ft8Ws) {
                this.ft8Ws.close();
            }
            if (typeof this.ft8RemoveKeyboardShortcuts === 'function') {
                this.ft8RemoveKeyboardShortcuts();
            }
            if (typeof this.ft8CloseDigitalBridge === 'function') {
                this.ft8CloseDigitalBridge();
            }
        }
    });

    window.vueInstance = app.mount('#app');
})();
