window.ENV_API_BASE = window.ENV_API_BASE || 'https://rg-arls-backend.azurewebsites.net';
window.ENV_BUILD_ID = window.ENV_BUILD_ID || '20260311-monthly-import-preview-ux-fix-v1';
window.ENV_GOOGLE_MAPS_API_KEY = window.ENV_GOOGLE_MAPS_API_KEY || '';

if (typeof window.__RG_ARLS_HANDLE_TAB_CLICK__ !== 'function') {
  window.__RG_ARLS_HANDLE_TAB_CLICK__ = (viewName) => {
    const view = String(viewName || '').trim();
    if (!view) return;
    if (typeof window.showView === 'function') {
      window.showView(view);
    }
  };
}

if (typeof window.__RG_ARLS_HANDLE_TOP_TAB__ !== 'function') {
  window.__RG_ARLS_HANDLE_TOP_TAB__ = (...args) => window.__RG_ARLS_HANDLE_TAB_CLICK__(...args);
}

if (typeof window.__RG_ARLS_SAFE_TAB_CLICK__ !== 'function') {
  window.__RG_ARLS_SAFE_TAB_CLICK__ = (...args) => window.__RG_ARLS_HANDLE_TAB_CLICK__(...args);
}

if (typeof window._RG_ARLS_HANDLE_TAB_CLICK !== 'function') {
  window._RG_ARLS_HANDLE_TAB_CLICK = (...args) => window.__RG_ARLS_HANDLE_TAB_CLICK__(...args);
}

if (typeof window.handleTopTab !== 'function') {
  window.handleTopTab = (...args) => window.__RG_ARLS_HANDLE_TAB_CLICK__(...args);
}
