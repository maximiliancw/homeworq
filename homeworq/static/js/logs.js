// Logs table with server-side pagination
function initLogsTable() {
  return $("#logsTable")
    .DataTable({
      serverSide: true,
      processing: true,
      responsive: true,
      stateSave: true,
      stateDuration: 60 * 60 * 24, // 24 hours
      ajax: {
        url: "/api/logs",
        // Convert DataTables request to our API format
        data: function (d) {
          return {
            offset: d.start,
            limit: d.length,
            draw: d.draw // Include draw parameter for proper state tracking
          };
        },
        // Transform our API response to DataTables format
        dataFilter: function (data) {
          const json = JSON.parse(data);
          return JSON.stringify({
            draw: json.draw || Date.now(),
            recordsTotal: json.total,
            recordsFiltered: json.total,
            data: json.items,
          });
        },
        error: function(xhr, error, thrown) {
          Alpine.store("data").notifier.showNotification(
            "Failed to load logs: " + (thrown || "Unknown error"),
            "error"
          );
        }
      },
      columns: [
        { 
          data: "job.name",
          title: "Job",
          className: "dt-body-left"
        },
        {
          data: "started_at",
          title: "Started At",
          render: (data) => data ? formatDate(data) : "N/A",
          className: "dt-body-center"
        },
        {
          data: "duration",
          title: "Duration",
          render: (data) => formatDuration(data),
          className: "dt-body-right"
        },
        {
          data: "status",
          title: "Status",
          render: (data) => getStatusEmoji(data),
          className: "dt-body-center"
        },
        {
          data: null,
          title: "Details",
          orderable: false,
          searchable: false,
          className: "dt-body-center",
          render: (data, type, row) => {
            return `<button onclick="showDetails('logs', '${row.id}')" 
                     class="secondary"
                     aria-label="View details for log ${row.id}">Details</button>`;
          }
        }
      ],
      pageLength: 25,
      lengthMenu: [
        [10, 25, 50, 100],
        [10, 25, 50, 100],
      ],
      order: [[1, "desc"]], // Sort by started_at by default
      language: {
        processing: "Loading...",
        search: "Search:",
        lengthMenu: "Show _MENU_ entries",
        info: "Showing _START_ to _END_ of _TOTAL_ entries",
        infoEmpty: "Showing 0 to 0 of 0 entries",
        infoFiltered: "(filtered from _MAX_ total entries)",
        emptyTable: "No data available in table",
      }
    })
    .on("preXhr.dt", function (e, settings, data) {
      Alpine.store("data").loading = true;
    })
    .on("xhr.dt", function (e, settings, json, xhr) {
      Alpine.store("data").loading = false;
    })
    .on("error.dt", function (e, settings, techNote, message) {
      Alpine.store("data").loading = false;
      Alpine.store("data").notifier.showNotification(
        "Error loading table data: " + message,
        "error"
      );
    });
}

$(document).ready(function () {
  const table = initLogsTable();
  let refreshInterval;

  // Only start auto-refresh if we're on the first page
  function startAutoRefresh() {
    if (table.page() === 0) {
      refreshInterval = setInterval(() => {
        table.ajax.reload(null, false);
      }, 10000);
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
