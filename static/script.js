function updateBatteryColor(level) {
        const batteryElement = document.getElementById("battery-indicator");
        if (level >= 81) {
            batteryElement.style.color = "#00ff00"; // Green
        } else if (level >= 51) {
            batteryElement.style.color = "#ffff00"; // Yellow
        } else if (level >= 21) {
            batteryElement.style.color = "#ff8800"; // Orange
        } else {
            batteryElement.style.color = "#ff0000"; // Red
        }
        }
        async function updateStatus() {
            try {
                const res = await fetch('/api/job_status');
                const enabled = await res.json();
                var runningButton = document.getElementById('running-button');
                runningButton.className = enabled ? 'running' : 'stopped';
                runningButton.textContent = enabled ? 'Running' : 'Idle';
            } catch (err) {
                console.error("Status check failed", err);
            }
        }

        async function refreshLogs() {
            try {
                const response = await fetch('/api/logs');
                const text = await response.text();
                const container = document.getElementById('logs-container');
                // Only update and scroll if content has actually changed
                if (container.textContent !== text) {
                    container.textContent = text || "No logs available.";
                    container.scrollTop = container.scrollHeight;
                }
                // Update refresh timestamp
                const now = new Date();
                document.getElementById('refresh-timestamp').innerHTML = `Last updated: ${now.toLocaleTimeString()}`;
            } catch (err) {
                console.error("Failed to fetch logs:", err);
            }
        }

        async function toggleJob() {
            await fetch('/api/toggle_Job', { method: 'POST' });
            updateStatus();
            refreshLogs();
        }

        async function clearLogs() {
            if (confirm("Are you sure you want to clear the logs?")) {
                await fetch('/api/clear_logs', { method: 'POST' });
                refreshLogs();
            }
        }

        async function checkCar(flash) {
            const endpoint = flash ? '/api/check_car_with_flashlights' : '/api/check_car';
            const response = await fetch(endpoint);
            const data = await response.json();
            
            if (data.batteryLevel !== undefined) {
                document.getElementById('battery-indicator').innerHTML = `<b>Battery:</b> ${data.batteryLevel}%`;
                document.getElementById('charge-indicator').innerHTML = `<b>Charge:</b> ${data.chargeStatus}`;
            }

            updateBatteryColor(data.batteryLevel)
            refreshLogs();
        }

        setInterval(refreshLogs, 60000);
        checkCar(false);
        refreshLogs();
        updateStatus();