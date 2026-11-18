const tabList = document.querySelector('.preview-tabs');
const tabs = [...tabList.querySelectorAll('[role="tab"]')];
const panels = tabs.map(tab => document.getElementById(tab.getAttribute('aria-controls')));

function activateTab(index) {
  tabs.forEach((tab, position) => {
    const active = position === index;
    tab.setAttribute('aria-selected', String(active));
    tab.tabIndex = active ? 0 : -1;
    panels[position].hidden = !active;
  });
}

tabs.forEach((tab, index) => {
  panels[index].setAttribute('role', 'tabpanel');
  panels[index].setAttribute('aria-labelledby', tab.id);
  panels[index].tabIndex = 0;
  tab.addEventListener('click', () => activateTab(index));
  tab.addEventListener('keydown', event => {
    const nextIndex = {
      ArrowLeft: (index - 1 + tabs.length) % tabs.length,
      ArrowRight: (index + 1) % tabs.length,
      Home: 0,
      End: tabs.length - 1,
    }[event.key];

    if (nextIndex === undefined) return;
    event.preventDefault();
    activateTab(nextIndex);
    tabs[nextIndex].focus();
  });
});

activateTab(0);
tabList.hidden = false;

const copyStatus = document.getElementById('copy-status');
let statusTimer;

document.querySelectorAll('[data-copy]').forEach(button => {
  const command = document.getElementById(button.dataset.copy);
  const label = button.querySelector('span');
  let resetTimer;

  button.hidden = false;
  button.addEventListener('click', async () => {
    let copied = false;

    try {
      await navigator.clipboard.writeText(command.textContent);
      copied = true;
    } catch {
      const range = document.createRange();
      range.selectNodeContents(command);
      const selection = window.getSelection();
      selection.removeAllRanges();
      selection.addRange(range);
    }

    window.clearTimeout(resetTimer);
    window.clearTimeout(statusTimer);
    button.toggleAttribute('data-copied', copied);
    label.textContent = copied ? 'Copied' : 'Selected';
    copyStatus.textContent = copied ? 'Commands copied to the clipboard.' : 'Commands selected. Use your device’s copy command.';

    resetTimer = window.setTimeout(() => {
      button.removeAttribute('data-copied');
      label.textContent = 'Copy';
    }, 3000);
    statusTimer = window.setTimeout(() => { copyStatus.textContent = ''; }, 3000);
  });
});
