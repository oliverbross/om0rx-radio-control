/**
 * Power Control Module
 * Handles server shutdown and restart functionality
 */

const PowerControl = {
    /**
     * Toggle the power menu visibility
     */
    togglePowerMenu() {
        this.showPowerMenu = !this.showPowerMenu;
    },

    /**
     * Close the power menu
     */
    closePowerMenu() {
        this.showPowerMenu = false;
    },

    /**
     * Request server shutdown
     */
    async shutdownServer() {
        this.closePowerMenu();
        
        if (!confirm('Are you sure you want to SHUTDOWN the server?\n\nYou will need to restart it manually.')) {
            return;
        }

        try {
            console.log('🛑 Sending shutdown request...');
            const response = await fetch('/api/shutdown', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                }
            });

            if (response.ok) {
                console.log('✓ Shutdown request sent');
                // Server will shut down, show offline banner
                this.serverOffline = true;
            } else {
                console.error('❌ Shutdown failed:', response.status);
                alert('Failed to shutdown server');
            }
        } catch (error) {
            console.error('❌ Shutdown error:', error);
            this.serverOffline = true; // Assume offline anyway since we can't connect
        }
    },

    /**
     * Request server restart
     */
    async restartServer() {
        this.closePowerMenu();
        
        if (!confirm('Are you sure you want to RESTART the server?\n\nThe application will be unavailable for a few seconds.')) {
            return;
        }

        try {
            console.log('🔄 Sending restart request...');
            const response = await fetch('/api/restart', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                }
            });

            if (response.ok) {
                console.log('✓ Restart request sent');
                // Server will restart, show offline banner temporarily
                this.serverOffline = true;
                
                // Try to reconnect after 3 seconds
                setTimeout(() => {
                    this.attemptReconnect();
                }, 3000);
            } else {
                console.error('❌ Restart failed:', response.status);
                alert('Failed to restart server');
            }
        } catch (error) {
            console.error('❌ Restart error:', error);
            this.serverOffline = true;
            
            // Try to reconnect after delay
            setTimeout(() => {
                this.attemptReconnect();
            }, 3000);
        }
    },

    /**
     * Attempt to reconnect to the server
     */
    async attemptReconnect() {
        console.log('🔌 Attempting to reconnect...');
        
        for (let attempt = 0; attempt < 15; attempt++) {
            try {
                const response = await fetch('/api/status', {
                    method: 'GET',
                    timeout: 2000
                });
                
                if (response.ok) {
                    console.log('✓ Server is back online!');
                    this.serverOffline = false;
                    
                    // Reconnect WebSocket
                    if (window.setupWebSocket) {
                        window.setupWebSocket();
                    }
                    return;
                }
            } catch (error) {
                // Still offline, wait and try again
            }
            
            // Wait before next attempt
            await new Promise(resolve => setTimeout(resolve, 1000));
        }
        
        console.error('❌ Failed to reconnect after multiple attempts');
        alert('Server is still offline. Please check the server status.');
    },

    /**
     * Handle WebSocket disconnection
     */
    onWebSocketDisconnect() {
        console.log('⚠️ WebSocket disconnected');
        this.serverOffline = true;
    },

    /**
     * Handle WebSocket reconnection
     */
    onWebSocketReconnect() {
        console.log('✓ WebSocket reconnected');
        this.serverOffline = false;
    }
};

// Export for use in Vue
if (typeof module !== 'undefined' && module.exports) {
    module.exports = PowerControl;
}