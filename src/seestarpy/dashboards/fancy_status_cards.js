function fancy_status_cards(data, dashboard, expandedCards) {
  dashboard.innerHTML = ''; // Clear previous cards

  const entries = Object.entries(data);

  entries.sort((a, b) => {
    const ta = parseFloat(a[1].Timestamp ?? 0);
    const tb = parseFloat(b[1].Timestamp ?? 0);
    return tb - ta;
  });

  for (const [key, entry] of entries) {
    const isExpanded = expandedCards.get(key) === true;

    const card = document.createElement('div');
    card.className = 'card';
    card.style.cursor = 'pointer';

    // Create combined title with color-coded state
    const stateVal = (entry.state ?? '').toLowerCase();
    const title = document.createElement('h3');

    const stateSpan = document.createElement('span');
    stateSpan.textContent = entry.state ?? 'n/a';
    if (stateVal === 'complete') {
      stateSpan.style.color = '#4caf50';
    } else if (stateVal === 'working') {
      stateSpan.style.color = '#ffc107';
    } else if (stateVal === 'fail') {
      stateSpan.style.color = '#f44336';
    } else {
      stateSpan.style.color = '#aaa';
    }

    title.innerHTML = `${key} : `;
    title.appendChild(stateSpan);
    card.appendChild(title);

    if (entry.error) {
      const error = document.createElement('div');
      error.className = 'error';
      error.textContent = `Error: ${entry.error}`;
      card.appendChild(error);
    }

    const jsonView = document.createElement('pre');
    jsonView.style.marginTop = '0.5em';
    jsonView.textContent = JSON.stringify(entry, null, 2);
    jsonView.style.display = isExpanded ? 'block' : 'none';
    card.appendChild(jsonView);

    card.addEventListener('click', () => {
      const current = expandedCards.get(key);
      expandedCards.set(key, !current);
      jsonView.style.display = !current ? 'block' : 'none';
    });

    dashboard.appendChild(card);
  }
}