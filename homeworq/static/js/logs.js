// Logs table with server-side pagination
function initLogsTable() {
  return $("#logsTable")
    .DataTable({
      serverSide: true,
      processing: true,
      ajax: {
        url: "/api/logs",
        // Convert DataTables request to our API format
        data: function (d) {
          return {
            offset: d.start,
            limit: d.length,
          };
        },
        // Transform our API response to DataTables format
        dataFilter: function (data) {
          const json = JSON.parse(data);
          return JSON.stringify({
            draw: Date.now(),
            recordsTotal: json.total,
            recordsFiltered: json.total,
            data: json.items,
          });
        },
      },
      columns: [
        { data: "job.name" },
        {
          data: "started_at",
          render: (data) => (data ? new Date(data).toLocaleString() : "N/A"),
        },
        {
          data: "duration",
          render: (data) => (data ? `${data.toFixed(2)}s` : "-"),
        },
        {
          data: "status",
          render: (data) => getStatusEmoji(data),
        },
        {
          data: null,
          render: (data, type, row) => {
            const details =
              row.error || JSON.stringify(row.log, null, 2) || "-";
            return `<button class="button button-small" onclick="showDetails('${
              row.job.id
            }', '${details.replace(/'/g, "\\'")}')">Details</button>`;
          },
        },
      ],
      pageLength: 25,
      lengthMenu: [
        [10, 25, 50, 100],
        [10, 25, 50, 100],
      ],
      order: [[1, "desc"]], // Sort by started_at by default
    })
    .on("preXhr.dt", function (e, settings, data) {
      Alpine.store("data").loading = true;
    })
    .on("draw.dt", function () {
      Alpine.store("data").loading = false;
    });
}

$(document).ready(function () {
  const table = initLogsTable();

  // Set up periodic updates
  setInterval(() => {
    table.ajax.reload(null, false);
  }, 60000);
});
