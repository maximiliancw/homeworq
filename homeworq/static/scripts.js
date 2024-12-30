$(document).ready(function () {
  // Utility functions
  const showLoader = () =>
    (document.getElementById("loader").style.display = "block");
  const hideLoader = () =>
    (document.getElementById("loader").style.display = "none");

  function showToast(message, type = "info") {
    const toast = document.createElement("div");
    toast.className = `toast toast-${type}`;
    toast.textContent = message;
    document.getElementById("toastContainer").appendChild(toast);
    setTimeout(() => toast.remove(), 3000);
  }

  function formatDate(dateString) {
    return new Date(dateString).toLocaleString();
  }

  function formatResult(result) {
    if (typeof result === "object" && result !== null) {
      return JSON.stringify(result, null, 2);
    }
    return result;
  }

  function showModal(title, content) {
    const modal = document.getElementById("modal");
    const modalTitle = modal.querySelector(".modal-title");
    const modalBody = modal.querySelector(".modal-body");

    modalTitle.textContent = title;
    modalBody.textContent = content;

    modal.showModal();
  }

  function closeModal() {
    const modal = document.getElementById("modal");
    modal.close();
  }

  function setLoadingButton(taskName, isLoading) {
    const button = document.querySelector(`#task-${taskName} .button`);
    if (isLoading) {
      button.classList.add("button-loading");
      button.dataset.originalText = button.textContent;
      button.textContent = "";
    } else {
      button.classList.remove("button-loading");
      button.textContent = button.dataset.originalText;
    }
  }

  function brandAnimation() {
    return {
      letters: "homeworq".split(""),
      isLoading: false,
      animationInterval: null,

      init() {
        // Listen for AJAX events using jQuery
        $(document).on("ajaxStart", () => {
          this.isLoading = true;
          this.startAnimation();
        });

        $(document).on("ajaxComplete", () => {
          this.isLoading = false;
          this.stopAnimation();
        });
      },

      getRandomPosition(index) {
        const x = Math.random() * 40 - 20;
        const y = Math.random() * 40 - 20;
        const rotation = Math.random() * 360;
        const delay = index * 50;

        return {
          "--x": `${x}px`,
          "--y": `${y}px`,
          "--rotation": `${rotation}deg`,
          "transition-delay": `${delay}ms`,
        };
      },

      startAnimation() {
        // Update positions periodically while loading
        this.animationInterval = setInterval(() => {
          // This will trigger a re-render of the positions
          this.isLoading = true;
        }, 150);
      },

      stopAnimation() {
        if (this.animationInterval) {
          clearInterval(this.animationInterval);
          this.animationInterval = null;
        }
      },
    };
  }
});
