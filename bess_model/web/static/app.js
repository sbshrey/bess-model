(() => {
  const showSessionFlash = () => {
    try {
      const success = sessionStorage.getItem("bess-flash-success");
      const error = sessionStorage.getItem("bess-flash-error");
      sessionStorage.removeItem("bess-flash-success");
      sessionStorage.removeItem("bess-flash-error");
      if (!success && !error) return;
      let flashStack = document.querySelector(".flash-stack");
      const pageShell = document.querySelector(".page-shell");
      if (!pageShell) return;
      if (!flashStack) {
        flashStack = document.createElement("section");
        flashStack.className = "flash-stack";
        const header = pageShell.querySelector("header");
        pageShell.insertBefore(flashStack, header?.nextSibling || pageShell.firstChild);
      }
      const createFlash = (msg, cls) => {
        const div = document.createElement("div");
        div.className = `flash ${cls}`;
        div.setAttribute("data-flash", "");
        const span = document.createElement("span");
        span.textContent = msg;
        div.appendChild(span);
        const btn = document.createElement("button");
        btn.type = "button";
        btn.className = "flash-close";
        btn.setAttribute("aria-label", "Dismiss");
        btn.innerHTML = "&times;";
        div.appendChild(btn);
        flashStack.appendChild(div);
      };
      if (success) createFlash(success, "flash-success");
      if (error) createFlash(error, "flash-error");
    } catch (_) {}
  };

  const initializeFlashDismiss = () => {
    const dismissFlash = (el) => {
      el.classList.add("flash-dismissing");
      el.addEventListener("transitionend", () => el.remove(), { once: true });
      setTimeout(() => el.remove(), 500);
    };

    document.addEventListener("click", (e) => {
      const btn = e.target.closest(".flash-close");
      if (btn) {
        const flash = btn.closest(".flash");
        if (flash) dismissFlash(flash);
      }
    });

    document.querySelectorAll("[data-flash]").forEach((el) => {
      setTimeout(() => dismissFlash(el), 6000);
    });
  };

  const initializeTabs = () => {
    document.querySelectorAll(".tabs-header").forEach((header) => {
      const wrapper = header.closest(".tabs-wrapper");
      if (!wrapper) return;
      const buttons = header.querySelectorAll(".tab-btn");
      const contents = wrapper.querySelectorAll(".tab-content");

      buttons.forEach((btn) => {
        btn.addEventListener("click", () => {
          buttons.forEach((b) => b.classList.remove("active"));
          contents.forEach((c) => c.classList.remove("active"));
          btn.classList.add("active");
          const target = wrapper.querySelector(btn.dataset.tabTarget);
          if (target) target.classList.add("active");
        });
      });
    });
  };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", () => {
      showSessionFlash();
      initializeFlashDismiss();
      initializeTabs();
    });
  } else {
    showSessionFlash();
    initializeFlashDismiss();
    initializeTabs();
  }

  const initializeSidebarToggle = () => {
    const layout = document.querySelector(".dashboard-layout");
    const toggles = Array.from(document.querySelectorAll("[data-sidebar-toggle]"));
    const sidebar = document.querySelector("[data-dashboard-sidebar]");
    if (!layout || toggles.length === 0) {
      return;
    }

    const storageKey = "bess-dashboard-sidebar-collapsed";
    const scrollKey = "bess-dashboard-sidebar-scroll";

    const syncToggleState = () => {
      const collapsed = layout.classList.contains("sidebar-collapsed");
      toggles.forEach((toggle) => {
        const collapsedLabel = toggle.classList.contains("button-small") ? "Expand" : "Expand Sidebar";
        const expandedLabel = toggle.classList.contains("button-small") ? "Collapse" : "Collapse Sidebar";
        toggle.textContent = collapsed ? collapsedLabel : expandedLabel;
        toggle.setAttribute("aria-expanded", collapsed ? "false" : "true");
      });
    };

    const setCollapsed = (collapsed) => {
      layout.classList.toggle("sidebar-collapsed", collapsed);
      try {
        window.localStorage.setItem(storageKey, collapsed ? "1" : "0");
      } catch (error) {
        /* restricted browser */
      }
      syncToggleState();
    };

    if (sidebar) {
      try {
        const savedScroll = window.sessionStorage.getItem(scrollKey);
        if (savedScroll) {
          sidebar.scrollTop = Number.parseInt(savedScroll, 10) || 0;
        }
      } catch (error) {
        /* restricted browser */
      }

      let scrollFrame = 0;
      sidebar.addEventListener("scroll", () => {
        if (scrollFrame) {
          window.cancelAnimationFrame(scrollFrame);
        }
        scrollFrame = window.requestAnimationFrame(() => {
          try {
            window.sessionStorage.setItem(scrollKey, String(sidebar.scrollTop));
          } catch (error) {
            /* restricted browser */
          }
          scrollFrame = 0;
        });
      });

      window.addEventListener("beforeunload", () => {
        try {
          window.sessionStorage.setItem(scrollKey, String(sidebar.scrollTop));
        } catch (error) {
          /* restricted browser */
        }
      });
    }

    try {
      if (window.localStorage.getItem(storageKey) === "1" && window.innerWidth > 980) {
        layout.classList.add("sidebar-collapsed");
      }
    } catch (error) {
      /* restricted browser */
    }

    syncToggleState();
    toggles.forEach((toggle) => {
      toggle.addEventListener("click", () => {
        setCollapsed(!layout.classList.contains("sidebar-collapsed"));
      });
    });

    window.addEventListener("resize", () => {
      if (window.innerWidth <= 980) {
        layout.classList.remove("sidebar-collapsed");
      } else {
        try {
          layout.classList.toggle("sidebar-collapsed", window.localStorage.getItem(storageKey) === "1");
        } catch (error) {
          /* restricted browser */
        }
      }
      syncToggleState();
    });
  };

  const initializeChartModal = () => {
    const modal = document.querySelector("[data-chart-modal]");
    if (!modal) {
      return;
    }

    const modalCanvas = modal.querySelector("[data-chart-modal-canvas]");
    const modalTitle = modal.querySelector("[data-chart-modal-title]");
    const modalSubtitle = modal.querySelector("[data-chart-modal-subtitle]");
    let scale = 1;

    const applyScale = () => {
      if (!modalCanvas) {
        return;
      }
      modalCanvas.style.setProperty("--chart-scale", String(scale));
    };

    const openModal = (button) => {
      const card = button.closest(".chart-card");
      const chartWrap = card?.querySelector(".chart-wrap");
      if (!chartWrap || !modalCanvas || !modalTitle || !modalSubtitle) {
        return;
      }

      modalCanvas.innerHTML = `<div class="chart-wrap">${chartWrap.innerHTML}</div>`;
      modalTitle.textContent = button.dataset.chartTitle || "Expanded Chart";
      modalSubtitle.textContent = button.dataset.chartSubtitle || "Inspect chart details.";
      scale = 1;
      applyScale();
      modal.hidden = false;
      document.body.classList.add("modal-open");
    };

    const closeModal = () => {
      modal.hidden = true;
      document.body.classList.remove("modal-open");
    };

    document.addEventListener("click", (event) => {
      const button = event.target.closest("[data-chart-open]");
      if (button) {
        openModal(button);
      }
    });

    modal.querySelectorAll("[data-chart-close]").forEach((button) => {
      button.addEventListener("click", closeModal);
    });

    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape" && !modal.hidden) {
        closeModal();
      }
    });
  };

  const initializeProgressBar = () => {
    document.addEventListener("submit", async (event) => {
      const form = event.target;
      const submitter = event.submitter;
      const actionUrl = submitter?.getAttribute("formaction") || form.getAttribute("action") || "";

      if (!actionUrl.includes("/run/simulate")) return;

      event.preventDefault();
      if (document.querySelector(".simulation-loading")) return;

      const overlay = document.createElement("div");
      overlay.className = "simulation-loading";
      overlay.setAttribute("role", "status");
      overlay.setAttribute("aria-live", "polite");

      const barWrap = document.createElement("div");
      barWrap.className = "simulation-loading-bar";
      const barFill = document.createElement("span");
      barFill.className = "simulation-loading-bar-fill";
      barWrap.appendChild(barFill);
      overlay.appendChild(barWrap);

      const card = document.createElement("div");
      card.className = "simulation-loading-card";

      const stageEl = document.createElement("p");
      stageEl.className = "simulation-loading-text";
      stageEl.textContent = "Starting\u2026";

      const detailEl = document.createElement("p");
      detailEl.className = "simulation-loading-detail";
      detailEl.textContent = "";

      const pctEl = document.createElement("p");
      pctEl.className = "simulation-loading-pct";
      pctEl.textContent = "0%";

      card.appendChild(stageEl);
      card.appendChild(detailEl);
      card.appendChild(pctEl);
      overlay.appendChild(card);
      document.body.prepend(overlay);

      const buttons = form.querySelectorAll("button[type='submit']");
      buttons.forEach((b) => {
        b.disabled = true;
      });

      try {
        const formData = new FormData(form);
        const res = await fetch("/api/run-simulation", { method: "POST", body: formData });
        if (!res.ok) throw new Error("Simulation request failed");

        const reader = res.body.getReader();
        const decoder = new TextDecoder();
        let buffer = "";
        let lastMessage = null;

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true });
          const lines = buffer.split("\n");
          buffer = lines.pop() || "";
          for (const line of lines) {
            if (!line.trim()) continue;
            try {
              const msg = JSON.parse(line);
              lastMessage = msg;
              if (msg.error) {
                stageEl.textContent = "Error";
                detailEl.textContent = msg.error;
                barFill.style.width = "0%";
                if (msg.redirect) {
                  sessionStorage.setItem("bess-flash-error", msg.error);
                  window.location.href = msg.redirect;
                  return;
                }
                break;
              }
              stageEl.textContent = msg.stage || stageEl.textContent;
              detailEl.textContent = msg.detail || "";
              const pct = msg.pct != null ? msg.pct : (msg.done ? 100 : 0);
              pctEl.textContent = `${Math.round(pct)}%`;
              barFill.style.width = `${pct}%`;
              if (msg.done && msg.redirect) {
                if (msg.message) sessionStorage.setItem("bess-flash-success", msg.message);
                window.location.href = msg.redirect;
                return;
              }
            } catch (_) {}
          }
        }

        if (lastMessage?.done && lastMessage?.redirect) {
          if (lastMessage.message) sessionStorage.setItem("bess-flash-success", lastMessage.message);
          window.location.href = lastMessage.redirect;
        } else if (lastMessage?.error && lastMessage?.redirect) {
          sessionStorage.setItem("bess-flash-error", lastMessage.error);
          window.location.href = lastMessage.redirect;
        }
      } catch (err) {
        stageEl.textContent = "Error";
        detailEl.textContent = err.message || "Simulation failed";
        barFill.style.width = "0%";
        buttons.forEach((b) => {
          b.disabled = false;
        });
      }
    });
  };

  const initializeSidebarResizer = () => {
    const resizer = document.querySelector(".sidebar-resizer");
    const sidebar = document.querySelector(".sidebar");
    const layout = document.querySelector(".dashboard-layout");

    if (!resizer || !sidebar || !layout) return;

    let isResizing = false;

    const savedWidth = localStorage.getItem("bess-dashboard-sidebar-width");
    if (savedWidth) {
      layout.style.setProperty("--sidebar-width", `${savedWidth}px`);
    }

    resizer.addEventListener("mousedown", () => {
      isResizing = true;
      resizer.classList.add("is-resizing");
      document.body.style.cursor = "col-resize";
      document.body.style.userSelect = "none";
    });

    document.addEventListener("mousemove", (e) => {
      if (!isResizing) return;
      const layoutRect = layout.getBoundingClientRect();
      let newWidth = e.clientX - layoutRect.left;

      if (newWidth < 250) newWidth = 250;
      if (newWidth > Math.min(800, window.innerWidth * 0.4)) newWidth = Math.min(800, window.innerWidth * 0.4);

      layout.style.setProperty("--sidebar-width", `${newWidth}px`);
    });

    document.addEventListener("mouseup", () => {
      if (isResizing) {
        isResizing = false;
        resizer.classList.remove("is-resizing");
        document.body.style.cursor = "";
        document.body.style.userSelect = "";
        const currentWidth = layout.style.getPropertyValue("--sidebar-width").replace("px", "");
        if (currentWidth) {
          localStorage.setItem("bess-dashboard-sidebar-width", currentWidth);
        }
      }
    });
  };

  const initializeInteractiveCharts = () => {
    const modal = document.querySelector("[data-chart-modal]");
    const modalCanvas = modal?.querySelector("[data-chart-modal-canvas]");
    const modalTitleElement = modal?.querySelector("[data-chart-modal-title]");

    let isDragging = false;
    let startX = 0;
    let brushGroup = null;
    let currentWrap = null;

    document.addEventListener("mousedown", (e) => {
      const wrap = e.target.closest(".chart-wrap");
      if (!wrap || e.target.closest(".reset-zoom-btn")) return;
      e.preventDefault();
      isDragging = true;
      currentWrap = wrap;
      const rect = wrap.getBoundingClientRect();
      startX = e.clientX - rect.left;

      brushGroup = document.createElement("div");
      brushGroup.className = "chart-brush";
      brushGroup.style.left = `${startX}px`;
      brushGroup.style.width = "0px";
      wrap.appendChild(brushGroup);
    });

    document.addEventListener("mousemove", (e) => {
      if (!isDragging || !brushGroup || !currentWrap) return;
      const rect = currentWrap.getBoundingClientRect();
      const currentX = e.clientX - rect.left;

      const clampedX = Math.max(0, Math.min(rect.width, currentX));
      const width = Math.abs(clampedX - startX);
      const left = Math.min(clampedX, startX);

      brushGroup.style.left = `${left}px`;
      brushGroup.style.width = `${width}px`;
    });

    const fetchAndRenderCharts = async (url, container) => {
       const chartGrid = container?.querySelector(".dashboard-chart-grid, .output-chart-grid, [data-chart-grid]");
       if (chartGrid) chartGrid.style.opacity = "0.5";
       if (modalCanvas && !modal.hidden) modalCanvas.style.opacity = "0.5";
       const isZoomed = url.includes("start_date=");
       try {
         const response = await fetch(url);
         if (!response.ok) throw new Error("Failed to fetch zoom bounds from Backend.");
         const cards = await response.json();
         if (cards.error) throw new Error(cards.error);

         const resetBtnHtml = isZoomed ? '<button class="reset-zoom-btn">Reset Zoom</button>' : "";
         let newHtml = "";
         for (const card of cards) {
            newHtml += `
             <article class="chart-card chart-card-large">
               <div class="chart-card-head">
                 <div>
                   <h3>${card.title}</h3>
                   <p>${card.subtitle}</p>
                 </div>
                 <button type="button" class="button button-ghost button-small" data-chart-open data-chart-title="${card.title}" data-chart-subtitle="${card.subtitle}">Expand</button>
               </div>
               <div class="chart-wrap chart-wrap-large">
                  ${resetBtnHtml}
                  ${card.svg}
               </div>
             </article>
            `;
            if (modalCanvas && !modal.hidden && modalTitleElement && modalTitleElement.textContent === card.title) {
                modalCanvas.innerHTML = `<div class="chart-wrap">${resetBtnHtml}${card.svg}</div>`;
            }
         }
         if (chartGrid) {
             chartGrid.innerHTML = newHtml;
             chartGrid.style.opacity = "1";
         }
         if (modalCanvas && !modal.hidden) {
             modalCanvas.style.opacity = "1";
         }
       } catch (err) {
         console.error(err);
         if (chartGrid) chartGrid.style.opacity = "1";
         if (modalCanvas && !modal.hidden) modalCanvas.style.opacity = "1";
       }
    };

    document.addEventListener("mouseup", async (e) => {
      if (!isDragging || !brushGroup || !currentWrap) return;
      isDragging = false;

      const wrap = currentWrap;
      const rect = wrap.getBoundingClientRect();
      const currentX = e.clientX - rect.left;
      const clampedX = Math.max(0, Math.min(rect.width, currentX));

      const left = Math.min(clampedX, startX);
      const right = Math.max(clampedX, startX);

      brushGroup.remove();
      brushGroup = null;
      currentWrap = null;

      if (right - left < 10) return;

      const svg = wrap.querySelector("svg");
      if (!svg) return;

      const xMin = parseFloat(svg.getAttribute("data-x-min"));
      const xMax = parseFloat(svg.getAttribute("data-x-max"));
      if (isNaN(xMin) || isNaN(xMax)) return;

      const svgWidth = parseFloat(svg.getAttribute("data-chart-width")) || 720;
      const scaleX = svgWidth / rect.width;
      const svgLeft = left * scaleX;
      const svgRight = right * scaleX;

      const leftPadding = 66;
      const rightPadding = 18;
      const chartWidth = svgWidth - leftPadding - rightPadding;

      let propStart = (svgLeft - leftPadding) / chartWidth;
      let propEnd = (svgRight - leftPadding) / chartWidth;
      propStart = Math.max(0, Math.min(1, propStart));
      propEnd = Math.max(0, Math.min(1, propEnd));
      if (propStart >= propEnd) return;

      const xSpan = xMax - xMin;
      const newXMin = xMin + propStart * xSpan;
      const newXMax = xMin + propEnd * xSpan;

      const d1 = new Date(newXMin * 1000);
      const d2 = new Date(newXMax * 1000);
      const pad = (n) => n.toString().padStart(2, '0');
      const s1 = `${d1.getFullYear()}-${pad(d1.getMonth()+1)}-${pad(d1.getDate())} ${pad(d1.getHours())}:${pad(d1.getMinutes())}:${pad(d1.getSeconds())}`;
      const s2 = `${d2.getFullYear()}-${pad(d2.getMonth()+1)}-${pad(d2.getDate())} ${pad(d2.getHours())}:${pad(d2.getMinutes())}:${pad(d2.getSeconds())}`;

      const container = wrap.closest(".dashboard-chart-panel, .output-charts-content");
      const filePath = container?.getAttribute("data-file-path");
      if (!filePath) return;

      const url = `/api/render-charts/${encodeURIComponent(filePath)}?start_date=${encodeURIComponent(s1)}&end_date=${encodeURIComponent(s2)}`;
      await fetchAndRenderCharts(url, container);
    });

    document.addEventListener("click", async (e) => {
       const resetBtn = e.target.closest(".reset-zoom-btn");
       if (resetBtn) {
          const wrap = resetBtn.closest(".chart-wrap");
          const container = wrap?.closest(".dashboard-chart-panel, .output-charts-content");
          const filePath = container?.getAttribute("data-file-path");
          if (!filePath) return;
          const url = `/api/render-charts/${encodeURIComponent(filePath)}`;
          await fetchAndRenderCharts(url, container);
       }
    });
  };

  const initializeRunSizing = () => {
    document.querySelectorAll("[data-run-sizing]").forEach((btn) => {
      btn.addEventListener("click", async () => {
        if (document.querySelector(".simulation-loading")) return;

        const configForm = btn.closest("main")?.querySelector("#config-form-full, form.config-visual-form");
        const formData = configForm ? new FormData(configForm) : null;

        const overlay = document.createElement("div");
        overlay.className = "simulation-loading";
        overlay.setAttribute("role", "status");
        overlay.setAttribute("aria-live", "polite");

        const barWrap = document.createElement("div");
        barWrap.className = "simulation-loading-bar";
        const barFill = document.createElement("span");
        barFill.className = "simulation-loading-bar-fill";
        barWrap.appendChild(barFill);
        overlay.appendChild(barWrap);

        const card = document.createElement("div");
        card.className = "simulation-loading-card";
        const stageEl = document.createElement("p");
        stageEl.className = "simulation-loading-text";
        stageEl.textContent = "Starting sizing sweep…";
        const detailEl = document.createElement("p");
        detailEl.className = "simulation-loading-detail";
        detailEl.textContent = "";
        const pctEl = document.createElement("p");
        pctEl.className = "simulation-loading-pct";
        pctEl.textContent = "0%";
        card.appendChild(stageEl);
        card.appendChild(detailEl);
        card.appendChild(pctEl);
        overlay.appendChild(card);
        document.body.prepend(overlay);

        document.querySelectorAll("[data-run-sizing]").forEach((b) => { b.disabled = true; });

        try {
          const res = await fetch("/api/run-sizing", {
            method: "POST",
            body: formData || undefined,
          });
          if (!res.ok) throw new Error("Sizing request failed");
          const reader = res.body.getReader();
          const decoder = new TextDecoder();
          let buffer = "";
          let lastMessage = null;
          while (true) {
            const { done, value } = await reader.read();
            if (done) break;
            buffer += decoder.decode(value, { stream: true });
            const lines = buffer.split("\n");
            buffer = lines.pop() || "";
            for (const line of lines) {
              if (!line.trim()) continue;
              try {
                const msg = JSON.parse(line);
                lastMessage = msg;
                if (msg.error) {
                  stageEl.textContent = "Error";
                  detailEl.textContent = msg.error;
                  barFill.style.width = "0%";
                  if (msg.redirect) {
                    sessionStorage.setItem("bess-flash-error", msg.error);
                    window.location.href = msg.redirect;
                    return;
                  }
                  break;
                }
                stageEl.textContent = msg.stage || stageEl.textContent;
                detailEl.textContent = msg.detail || "";
                const pct = msg.pct != null ? msg.pct : (msg.done ? 100 : 0);
                pctEl.textContent = `${Math.round(pct)}%`;
                barFill.style.width = `${pct}%`;
                if (msg.done && msg.redirect) {
                  if (msg.message) sessionStorage.setItem("bess-flash-success", msg.message);
                  window.location.href = msg.redirect;
                  return;
                }
              } catch (_) {}
            }
          }
          if (lastMessage?.done && lastMessage?.redirect) {
            if (lastMessage.message) sessionStorage.setItem("bess-flash-success", lastMessage.message);
            window.location.href = lastMessage.redirect;
          } else if (lastMessage?.error && lastMessage?.redirect) {
            sessionStorage.setItem("bess-flash-error", lastMessage.error);
            window.location.href = lastMessage.redirect;
          }
        } catch (err) {
          stageEl.textContent = "Error";
          detailEl.textContent = err.message || "Sizing failed";
          barFill.style.width = "0%";
          sessionStorage.setItem("bess-flash-error", err.message || "Sizing failed");
          setTimeout(() => window.location.reload(), 1500);
        } finally {
          document.querySelectorAll("[data-run-sizing]").forEach((b) => { b.disabled = false; });
        }
      });
    });
  };

  const initializeDashboardFileTabs = () => {
    const panel = document.querySelector(".dashboard-chart-panel");
    const fileTabs = document.querySelectorAll(".file-tab");
    const chartGrid = document.querySelector(".dashboard-chart-grid, [data-chart-grid]");
    const modal = document.querySelector("[data-chart-modal]");
    const modalCanvas = modal?.querySelector("[data-chart-modal-canvas]");
    const modalTitleElement = modal?.querySelector("[data-chart-modal-title]");
    const fileInsightsPanel = document.querySelector(".file-insights-panel");

    if (!panel || !fileTabs.length || !chartGrid) return;

    const fetchAndRenderCharts = async (filePath, startDate, endDate) => {
      chartGrid.style.opacity = "0.5";
      if (modalCanvas && modal && !modal.hidden) modalCanvas.style.opacity = "0.5";
      let url = `/api/render-charts/${encodeURIComponent(filePath)}`;
      if (startDate || endDate) {
        const params = new URLSearchParams();
        if (startDate) params.set("start_date", startDate);
        if (endDate) params.set("end_date", endDate);
        url += "?" + params.toString();
      }
      try {
        const response = await fetch(url);
        if (!response.ok) throw new Error("Failed to fetch charts");
        const cards = await response.json();
        if (cards.error) throw new Error(cards.error);
        let html = "";
        for (const card of cards) {
          html += `
            <article class="chart-card chart-card-large">
              <div class="chart-card-head">
                <div><h3>${card.title}</h3><p>${card.subtitle}</p></div>
                <button type="button" class="button button-ghost button-small" data-chart-open data-chart-title="${card.title}" data-chart-subtitle="${card.subtitle}">Expand</button>
              </div>
              <div class="chart-wrap chart-wrap-large">${card.svg}</div>
            </article>
          `;
        }
        chartGrid.innerHTML = html || '<p class="empty-state">No charts for this file.</p>';
        panel.setAttribute("data-file-path", filePath);
      } catch (err) {
        chartGrid.innerHTML = `<p class="empty-state">Could not load charts: ${err.message}</p>`;
      }
      chartGrid.style.opacity = "1";
      if (modalCanvas && modal && !modal.hidden) modalCanvas.style.opacity = "1";
    };

    fileTabs.forEach((tab) => {
      tab.addEventListener("click", () => {
        const filePath = tab.dataset.filePath;
        if (!filePath) return;
        fileTabs.forEach((t) => t.classList.remove("active"));
        tab.classList.add("active");
        const dateForm = panel.querySelector(".date-filter-form");
        const startDate = dateForm?.querySelector('input[name="start_date"]')?.value || "";
        const endDate = dateForm?.querySelector('input[name="end_date"]')?.value || "";
        const newUrl = new URL(window.location);
        newUrl.searchParams.set("file", filePath);
        window.history.pushState({}, "", newUrl);
        fetchAndRenderCharts(filePath, startDate, endDate);
      });
    });
  };

  initializeDashboardFileTabs();
  initializeSidebarToggle();
  initializeSidebarResizer();
  initializeChartModal();
  initializeProgressBar();
  initializeRunSizing();
  initializeInteractiveCharts();
})();
