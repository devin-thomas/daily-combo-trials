(() => {
  const allowedUrl = (value) => {
    if (typeof value !== "string") return false;
    try {
      const url = new URL(value, window.location.origin);
      return url.hostname === "daily-combo-trials.vercel.app"
        && url.pathname !== "/setup"
        && !url.pathname.startsWith("/setup/");
    } catch (error) {
      if (error instanceof TypeError) return false;
      throw error;
    }
  };

  window.va = window.va || function () {
    (window.vaq = window.vaq || []).push(arguments);
  };
  window.va("beforeSend", (event) => (
    allowedUrl(window.location.href) && allowedUrl(event.url) ? event : null
  ));

})();
