let currentZoomHours = 24;

function setZoom(hours) {
    currentZoomHours = hours;
    refreshTimeline();
}

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

                // Fetch next run time
                const nextRes = await fetch('/api/next_run');
                const nextRun = await nextRes.json();
                document.getElementById('next-run').textContent = `Next run: ${nextRun}`;
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

        async function refreshTimeline() {
            try {
                const res = await fetch('/api/history');
                const history = await res.json();
                const container = document.getElementById('timeline-container');
                container.innerHTML = '<div class="timeline-row row-slots"></div><div class="timeline-row row-charging"></div>';
                
                const slotRow = container.querySelector('.row-slots');
                const chargeRow = container.querySelector('.row-charging');
                
                const now = new Date().getTime();
                let startLimit, endLimit;

                if (currentZoomHours > 0) {
                    startLimit = now - (currentZoomHours * 60 * 60 * 1000);
                    endLimit = now;
                    document.getElementById('label-start').textContent = `${currentZoomHours}h ago`;
                    document.getElementById('label-mid').textContent = `${currentZoomHours / 2}h ago`;
                    document.getElementById('label-end').textContent = `Now`;
                } else {
                    const hours = Math.abs(currentZoomHours);
                    startLimit = now;
                    endLimit = now + (hours * 60 * 60 * 1000);
                    document.getElementById('label-start').textContent = `Now`;
                    document.getElementById('label-mid').textContent = `In ${hours / 2}h`;
                    document.getElementById('label-end').textContent = `In ${hours}h`;
                }
                
                const zoomMs = endLimit - startLimit;

                // Update Button States
                document.querySelectorAll('.zoom-btn').forEach(btn => {
                    btn.classList.toggle('active', parseInt(btn.getAttribute('data-hours')) === currentZoomHours);
                });

                // Draw vertical grid lines every 30 minutes
                const thirtyMinMs = 30 * 60 * 1000;
                for (let t = Math.ceil(startLimit / thirtyMinMs) * thirtyMinMs; t <= endLimit; t += thirtyMinMs) {
                    const pos = ((t - startLimit) / zoomMs) * 100;
                    const line = document.createElement('div');
                    line.className = 'grid-line';
                    line.style.left = `${pos}%`;
                    container.appendChild(line);
                }

                history.forEach(entry => {
                    if (entry.event === 'slots_discovered') {
                        entry.details.slots.forEach(slot => {
                            const sStart = new Date(slot.startDt).getTime();
                            const sEnd = new Date(slot.endDt).getTime();
                            if (sEnd < startLimit || sStart > endLimit) return;

                            const sLeft = ((Math.max(sStart, startLimit) - startLimit) / zoomMs) * 100;
                            const sWidth = ((Math.min(sEnd, endLimit) - Math.max(sStart, startLimit)) / zoomMs) * 100;
                            
                            const div = document.createElement('div');
                            div.className = 'segment seg-slot';
                            div.style.left = `${sLeft}%`;
                            div.style.width = `${sWidth}%`;
                            const startDate = new Date(slot.startDt);
                            const endDate = new Date(slot.endDt);
                            div.title = `Slot: ${startDate.toLocaleDateString()} ${startDate.toLocaleTimeString()} - ${endDate.toLocaleTimeString()}`;
                            slotRow.appendChild(div);
                        });
                    } else if (entry.event === 'car_status_update' && entry.details.is_charging) {
                        const entryTime = new Date(entry.timestamp).getTime();
                        if (entryTime < startLimit || entryTime > endLimit) return;

                        const leftPos = ((entryTime - startLimit) / zoomMs) * 100;
                        // Show 30 min block for charging status
                        const durationMs = 30 * 60 * 1000;
                        const width = (durationMs / zoomMs) * 100;
                        const div = document.createElement('div');
                        div.className = 'segment seg-charge';
                        div.style.left = `${leftPos}%`;
                        div.style.width = `${width}%`;
                        div.textContent = `${entry.details.battery_level}%`;
                        const chargeTime = new Date(entry.timestamp);
                        div.title = `Charging: ${chargeTime.toLocaleDateString()} ${chargeTime.toLocaleTimeString()} (${entry.details.battery_level}%)`;
                        chargeRow.appendChild(div);
                    }
                });
            } catch (err) { console.error("Timeline refresh failed", err); }
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
        setInterval(updateStatus, 60000);
        checkCar(false);
        refreshLogs();
        updateStatus();
        refreshTimeline();
