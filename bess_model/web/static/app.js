(() => {
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
        // Ignore storage failures in restricted browsers.
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
        // Ignore storage failures in restricted browsers.
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
            // Ignore storage failures in restricted browsers.
          }
          scrollFrame = 0;
        });
      });

      window.addEventListener("beforeunload", () => {
        try {
          window.sessionStorage.setItem(scrollKey, String(sidebar.scrollTop));
        } catch (error) {
          // Ignore storage failures in restricted browsers.
        }
      });
    }

    try {
      if (window.localStorage.getItem(storageKey) === "1" && window.innerWidth > 980) {
        layout.classList.add("sidebar-collapsed");
      }
    } catch (error) {
      // Ignore storage failures in restricted browsers.
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
          // Ignore storage failures in restricted browsers.
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

      modalCanvas.innerHTML = chartWrap.innerHTML;
      modalTitle.textContent = button.dataset.chartTitle || "Expanded Chart";
      modalSubtitle.textContent = button.dataset.chartSubtitle || "Inspect chart details with zoom controls.";
      scale = 1;
      applyScale();
      modal.hidden = false;
      document.body.classList.add("modal-open");
    };

    const closeModal = () => {
      modal.hidden = true;
      document.body.classList.remove("modal-open");
    };

    document.querySelectorAll("[data-chart-open]").forEach((button) => {
      button.addEventListener("click", () => openModal(button));
    });

    modal.querySelectorAll("[data-chart-close]").forEach((button) => {
      button.addEventListener("click", closeModal);
    });

    modal.querySelector("[data-chart-zoom-in]")?.addEventListener("click", () => {
      scale = Math.min(3, scale + 0.2);
      applyScale();
    });

    modal.querySelector("[data-chart-zoom-out]")?.addEventListener("click", () => {
      scale = Math.max(0.6, scale - 0.2);
      applyScale();
    });

    modal.querySelector("[data-chart-zoom-reset]")?.addEventListener("click", () => {
      scale = 1;
      applyScale();
    });

    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape" && !modal.hidden) {
        closeModal();
      }
    });
  };

  const initializeProgressBar = () => {
    document.addEventListener("submit", (event) => {
      const form = event.target;
      // We check if the submitter (like a button with formaction) overrides the action
      // Or fallback to the form's action itself.
      const submitter = event.submitter;
      const actionUrl = submitter?.getAttribute("formaction") || form.getAttribute("action") || "";
      
      if (actionUrl.includes("/run/simulate") || actionUrl.includes("/run/size")) {
        // Prevent stacking if somehow clicked twice
        if (!document.querySelector(".global-progress")) {
          const progress = document.createElement("div");
          progress.className = "global-progress";
          document.body.prepend(progress);
          
          // disable submit buttons inside this form to prevent double submission
          const buttons = form.querySelectorAll("button[type='submit']");
          buttons.forEach(b => {
             b.style.pointerEvents = "none";
             b.style.opacity = "0.7";
          });
        }
      }
    });
  };

  const initializeSidebarResizer = () => {
    const resizer = document.querySelector(".sidebar-resizer");
    const sidebar = document.querySelector(".sidebar");
    const layout = document.querySelector(".dashboard-layout");
    
    if (!resizer || !sidebar || !layout) return;

    let isResizing = false;
    
    // Load previously saved width
    const savedWidth = localStorage.getItem("bess-dashboard-sidebar-width");
    if (savedWidth) {
      layout.style.setProperty("--sidebar-width", `${savedWidth}px`);
    }

    resizer.addEventListener("mousedown", (e) => {
      isResizing = true;
      resizer.classList.add("is-resizing");
      document.body.style.cursor = "col-resize";
      document.body.style.userSelect = "none";
    });

    document.addEventListener("mousemove", (e) => {
      if (!isResizing) return;
      const layoutRect = layout.getBoundingClientRect();
      let newWidth = e.clientX - layoutRect.left;
      
      // Enforce min/max widths
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

  initializeSidebarToggle();
  initializeSidebarResizer();
  initializeChartModal();
  initializeProgressBar();
})();
