(() => {
  const config = JSON.parse(document.getElementById("web-analytics-config").textContent);
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

  if (!config.custom_events) return;

  document.addEventListener("submit", (event) => {
    const form = event.target;
    if (!(form instanceof HTMLFormElement)) return;
    const name = form.dataset.analyticsEvent;
    if (name === "randomize" || name === "back_to_daily") {
      window.va("event", { name });
    }
  });

  document.addEventListener("click", (event) => {
    if (!(event.target instanceof Element)) return;
    const link = event.target.closest("a[data-analytics-event]");
    if (!link) return;
    if (link.dataset.analyticsEvent === "open_history") {
      window.va("event", { name: "open_history" });
    } else if (link.dataset.analyticsEvent === "outbound_source_click") {
      const kind = link.dataset.analyticsKind;
      if (!["description_source", "artwork_source", "game_reference", "combined_source"].includes(kind)) return;
      const destination = new URL(link.href);
      if (!["https:", "http:"].includes(destination.protocol)) return;
      const host = destination.hostname.toLowerCase().replace(/\.$/, "").replace(/^www\./, "");
      window.va("event", { name: "outbound_source_click", data: { host, kind } });
    }
  });
})();
