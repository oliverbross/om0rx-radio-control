// Navigation for the dedicated Station Management popup.
(function () {
    'use strict';

    function returnToRadioControl(currentWindow = window) {
        const opener = currentWindow.opener;
        if (opener && !opener.closed) {
            opener.focus?.();
            currentWindow.close?.();
            return 'opener';
        }
        currentWindow.location.assign('/');
        return 'navigate';
    }

    function handleClick(event) {
        if (event.target.closest?.('[data-station-navigation="return"]')) {
            returnToRadioControl();
        }
    }

    window.StationWindowNavigation = Object.freeze({ returnToRadioControl });
    document.addEventListener('click', handleClick);
}());
