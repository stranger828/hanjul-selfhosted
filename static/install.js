// Installation only: no memo or attachment responses are cached here.
(() => {
  let pending;
  const buttons = [...document.querySelectorAll('.install-app')];
  const standalone = matchMedia('(display-mode: standalone)');
  const hide = () => buttons.forEach(button => { button.hidden = true; });
  window.addEventListener('beforeinstallprompt', event => {
    event.preventDefault();
    pending = event;
    if (!standalone.matches) buttons.forEach(button => { button.hidden = false; });
  });
  window.addEventListener('appinstalled', () => { pending = null; hide(); });
  standalone.addEventListener('change', () => { if (standalone.matches) hide(); });
  buttons.forEach(button => button.addEventListener('click', async () => {
    if (!pending) return;
    const prompt = pending;
    pending = null;
    hide();
    try {
      await prompt.prompt();
      await prompt.userChoice;
    } catch {
      document.querySelectorAll('.install-help').forEach(help => {
        help.hidden = false;
        help.textContent = '브라우저 메뉴에서 앱 설치 또는 홈 화면에 추가를 선택해 주세요.';
      });
    }
  }));
})();
