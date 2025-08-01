let equatorialLatitude = 0;
let equModeEnabled = false;

function drawAltitude(ctx, angleDeg = 0) {
  const centerX = 60;
  const centerY = 60;
  const radius = 50;
  const latOffset = equModeEnabled ? equatorialLatitude : 0;
  const angleRad = (180 + angleDeg) * Math.PI / 180;

  ctx.clearRect(0, 0, 120, 120);
  ctx.save();
  ctx.translate(centerX, centerY);
  if (equModeEnabled) {
    ctx.rotate(latOffset * Math.PI / 180);
  }
  ctx.translate(-centerX, -centerY);

  // Draw semicircle ("D" shape)
  ctx.beginPath();
  ctx.arc(centerX, centerY, radius, Math.PI / 2, 3 * Math.PI / 2);
  ctx.strokeStyle = '#888';
  ctx.lineWidth = 1;
  ctx.stroke();

  // Draw mount orientation line (yellow from -90 to +90)
  // if (equModeEnabled) {
  ctx.beginPath();
  ctx.moveTo(centerX + radius * Math.cos(Math.PI / 2), centerY + radius * Math.sin(Math.PI / 2));
  ctx.lineTo(centerX + radius * Math.cos(3 * Math.PI / 2), centerY + radius * Math.sin(3 * Math.PI / 2));
  ctx.strokeStyle = 'yellow';
  ctx.lineWidth = 1.5;
  ctx.stroke();
  // }

  // Draw indicator needle
  ctx.beginPath();
  ctx.moveTo(centerX, centerY);
  ctx.lineTo(centerX + radius * Math.cos(angleRad), centerY + radius * Math.sin(angleRad));
  ctx.strokeStyle = 'red';
  ctx.lineWidth = 2;
  ctx.stroke();

  // Ticks for -90, 0, +90
  const ticks = [
    { angle: 0, label: '+90' },
    { angle: 90, label: '0' },
    { angle: 180, label: '-90' }
  ];

  ctx.font = '10px monospace';
  ctx.fillStyle = '#aaa';
  for (const { angle, label } of ticks) {
    const rad = (angle - 90) * Math.PI / 180;
    const x = centerX + (radius + 5) * Math.cos(rad);
    const y = centerY + (radius + 5) * Math.sin(rad) + 3;
    ctx.fillText(label, x - ctx.measureText(label).width / 2, y);
  }

  ctx.restore();
}

function drawAzimuth(ctx, angleDeg = 0) {
  const center = 60;
  const radius = 50;
  const angleRad = (angleDeg - 90) * Math.PI / 180;

  ctx.clearRect(0, 0, 120, 120);
  ctx.beginPath();
  ctx.moveTo(center, center);
  ctx.lineTo(center + radius * Math.cos(angleRad), center + radius * Math.sin(angleRad));
  ctx.strokeStyle = 'red';
  ctx.lineWidth = 2;
  ctx.stroke();

  const ticks = [
    { angle: 0, label: 'N' },
    { angle: 90, label: 'E' },
    { angle: 180, label: 'S' },
    { angle: 270, label: 'W' }
  ];

  ctx.font = '10px monospace';
  ctx.fillStyle = '#aaa';
  for (const { angle, label } of ticks) {
    const rad = (angle - 90) * Math.PI / 180;
    const x = center + 45 * Math.cos(rad);
    const y = center + 45 * Math.sin(rad) + 3;
    ctx.fillText(label, x - ctx.measureText(label).width / 2, y);
  }
}

function updateAltAzFromJson(json) {
  for (const entry of Object.values(json)) {
    if (entry.Event === 'get_device_state' && entry.result?.mount?.equ_mode === true) {
      equModeEnabled = true;
      if (Array.isArray(entry.result.location_lon_lat)) {
        equatorialLatitude = parseFloat(entry.result.location_lon_lat[1]) || 0;
      }
    }
    if (entry.Event === 'scope_get_horiz_coord' && Array.isArray(entry.result) && entry.result.length === 2) {
      const alt = parseFloat(entry.result[0]);
      const az = parseFloat(entry.result[1]);
      drawAltitude(document.getElementById('altitudeCanvas').getContext('2d'), alt);
      drawAzimuth(document.getElementById('azimuthCanvas').getContext('2d'), az);
      document.getElementById('altValue').textContent = `Alt: ${Math.round(alt)}°`;
      document.getElementById('azValue').textContent = `Az: ${Math.round(az)}°`;
    }
  }

  updateStatusPanel(json);
}

function updateStatusPanel(state) {
  const statusContainer = document.getElementById('statusPanel');
  if (!statusContainer) return;

  const get = (path, defaultVal = '—') => {
    try {
      return path.reduce((obj, key) => obj?.[key], state) ?? defaultVal;
    } catch {
      return defaultVal;
    }
  };

  const fields = [
    { val: 'Battery',         label: get(['get_device_state', 'result', 'pi_status', 'battery_capacity']) + "%", type: 'int' },
    { label: 'EQ',            val: get(['get_device_state', 'result', 'mount', 'equ_mode']), type: 'bool' },
    { label: 'TRACK',         val: get(['get_device_state', 'result', 'mount', 'tracking']), type: 'bool' },
    { label: 'LP',            val: get(['iscope_get_app_state', 'result', 'View', 'lp_filter']), type: 'bool' },
    { val: 'Focus',           label: get(['get_device_state', 'result', 'focuser', 'step']), type: 'int' },
    { val: 'Stack Exp (ms)',  label: get(['get_device_state', 'result', 'setting', 'exp_ms', 'stack_l']) / 1000 + "s", type: 'int' },
    { val: 'Stage',           label: get(['iscope_get_app_state', 'result', 'View', 'stage']), type: 'str' },
  ];

  statusContainer.innerHTML = fields.map(({ label, val, type }) => {
    let className = 'status-unknown';
    if (type === 'bool') className = val === true ? 'status-true' : val === false ? 'status-false' : 'status-unknown';
    const labelSpan = `<span class="${className}">${label}</span>`;
    return `<div class="status-indicator">${labelSpan}</div>`;
    // return `<div class="status-indicator">${label}: <span class="${className}">${val}</span></div>`;
    // return `<div class="status-indicator">${labelSpan} <span class="${className}">${val}</span></div>`;
  }).join('\n');
}


