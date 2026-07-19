console.log('WinKeyer modules loaded');

if (typeof WinKeyerUI !== 'undefined') {
    document.addEventListener('vue-mounted', () => {
        if (window.vueInstance) window.winKeyerUI = new WinKeyerUI(window.vueInstance);
    }, { once: true });
} else {
    console.warn('WinKeyer UI is unavailable');
}
