// Jobs table with client-side processing
function initJobsTable() {
  return initDataTable("jobsTable", {
    ajax: {
      url: "/api/jobs",
      dataSrc: "",
      error: function(xhr, error, thrown) {
        handleDataTableError(this, thrown || "Unknown error");
      }
    },
    columns: [
      { 
        data: "name",
        title: "Name",
        className: "dt-body-left"
      },
      {
        data: "params",
        title: "Params",
        className: "dt-body-left",
        render: (data) =>
          data ? `<pre>${JSON.stringify(data, null, 2)}</pre>` : "N/A",
      },
      {
        data: "last_run",
        title: "Last Run",
        className: "dt-body-center",
        render: (data) => (data ? new Date(data).toLocaleString() : "Never"),
      },
      {
        data: "next_run",
        title: "Next Run",
        className: "dt-body-center",
        render: (data) =>
          data ? new Date(data).toLocaleString() : "Not scheduled",
      },
      {
        data: "id",
        title: "Actions",
        className: "dt-body-center",
        orderable: false,
        searchable: false,
        render: (data) => `
          <button onclick="showDetails('jobs', '${data}')" 
                  class="secondary"
                  aria-label="View details for job ${data}">Details</button>
        `,
      },
    ],
    pageLength: 25,
    order: [[3, "desc"]], // Sort by next_run by default
    responsive: true,
    stateSave: true,
    stateDuration: 60 * 60 * 24, // 24 hours
  })
  .on("preXhr.dt", function (e, settings, data) {
    Alpine.store("data").loading = true;
  })
  .on("xhr.dt", function (e, settings, json, xhr) {
    Alpine.store("data").loading = false;
  })
  .on("error.dt", function (e, settings, techNote, message) {
    handleDataTableError(this, message);
  });
}

function showJobDetails(id) {
  window.location.href = `/jobs/${id}`;
}

$(document).ready(function () {
  const table = initJobsTable();
  let refreshInterval;

  // Only start auto-refresh if we're on the first page
  function startAutoRefresh() {
    if (table.page() === 0) {
      refreshInterval = setInterval(() => {
        table.ajax.reload(null, false);
      }, 30000);
    }
  }

  function stopAutoRefresh() {
    if (refreshInterval) {
      clearInterval(refreshInterval);
      refreshInterval = null;
    }
  }

  // Start auto-refresh initially
  startAutoRefresh();

  // Handle page changes
  table.on('page.dt', function() {
    if (table.page() === 0) {
      startAutoRefresh();
    } else {
      stopAutoRefresh();
    }
  });
});
