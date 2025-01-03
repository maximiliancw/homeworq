// Jobs table with client-side processing
function initJobsTable() {
  return $("#jobsTable").DataTable({
    ajax: {
      url: "/api/jobs",
      dataSrc: "",
    },
    columns: [
      { data: "name" },
      {
        data: "params",
        render: (data) =>
          data ? `<pre>${JSON.stringify(data, null, 2)}</pre>` : "N/A",
      },
      {
        data: "last_run",
        render: (data) => (data ? new Date(data).toLocaleString() : "Never"),
      },
      {
        data: "next_run",
        render: (data) =>
          data ? new Date(data).toLocaleString() : "Not scheduled",
      },
      {
        data: "id",
        orderable: false,
        searchable: false,
        render: (data) => `
                      <button onclick="showJobDetails('${data}')">Details</button>
                `,
      },
    ],
    pageLength: 25,
    order: [[4, "desc"]], // Sort by next_run by default
  });
}

function showJobDetails(id) {
  window.location.href = `/jobs/${id}`;
}

$(document).ready(function () {
  const table = initJobsTable();

  // Set up periodic updates
  setInterval(() => {
    table.ajax.reload(null, false);
  }, 30000);
});
