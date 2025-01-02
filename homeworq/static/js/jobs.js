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
        render: (data) => `
                    <button onclick="showJobHistory('${data}')" class="secondary">History</button>
                    <button onclick="deleteJob('${data}')" class="contrast">Delete</button>
                `,
      },
    ],
    pageLength: 25,
    order: [[4, "desc"]], // Sort by next_run by default
  });
}

$(document).ready(function () {
  const table = initJobsTable();

  // Set up periodic updates
  setInterval(() => {
    table.ajax.reload(null, false);
  }, 30000);
});
