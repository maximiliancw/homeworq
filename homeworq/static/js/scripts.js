const showLoader = () =>
  (document.getElementById("loader").style.display = "block");
const hideLoader = () =>
  (document.getElementById("loader").style.display = "none");

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

function getStatusEmoji(status) {
  return (
    {
      completed: "✅",
      failed: "❌",
      running: "⏳",
      pending: "⏰",
    }[status] || "❔"
  );
}

function formatTimeAgo(date) {
  const seconds = Math.floor((new Date() - new Date(date)) / 1000);
  const intervals = {
    year: 31536000,
    month: 2592000,
    week: 604800,
    day: 86400,
    hour: 3600,
    minute: 60,
  };

  for (const [unit, secondsInUnit] of Object.entries(intervals)) {
    const interval = Math.floor(seconds / secondsInUnit);
    if (interval >= 1) {
      return `${interval} ${unit}${interval === 1 ? "" : "s"} ago`;
    }
  }
  return "just now";
}

function formatDuration(seconds) {
  if (typeof seconds == "number") {
    return `${seconds.toFixed(1)}s`;
  }
  return seconds;
}

function formatDate(date) {
  return new Date(date).toLocaleString();
}

$(document).ready(async () => {
  const store = Alpine.store("data");
  var path = window.location.pathname;
  // Add 'active' class to both desktop and mobile navigation links
  if (path === "/") {
    $("#nav-dashboard").addClass("active");
    $(".nav-mobile-items a[href='/']").addClass("active");
  } else if (path.startsWith("/tasks")) {
    $("#nav-tasks").addClass("active");
    $(".nav-mobile-items a[href='/tasks']").addClass("active");
  } else if (path.startsWith("/jobs")) {
    $("#nav-jobs").addClass("active");
    $(".nav-mobile-items a[href='/jobs']").addClass("active");
  } else if (path.startsWith("/logs")) {
    $("#nav-logs").addClass("active");
    $(".nav-mobile-items a[href='/logs']").addClass("active");
  }
});
