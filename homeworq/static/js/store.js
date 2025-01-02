document.addEventListener("alpine:init", () => {
  Alpine.store("data", {
    search: "",
    jobs: [],
    tasks: [],
    logs: {},
    analytics: {
      recentActivity: [],
      upcomingExecutions: [],
      executionHistory: [],
      taskDistribution: [],
    },

    // Computed metrics now only depend on analytics data
    metrics() {
      const totalLogs = this.logs.items.length;
      const errors = this.analytics.recentActivity.filter(
        (log) => log.status === "failed"
      );
      const errorRate = totalLogs
        ? Math.round((errors.length / totalLogs) * 100)
        : 0;

      return {
        tasks: this.tasks.length,
        jobs: this.jobs.length,
        logs: totalLogs,
        errors: { count: errors.length, rate: errorRate },
      };
    },

    // Specific fetch methods for each data type
    async fetchDashboardData() {
      await Promise.all([
        this.fetchTasks(),
        this.fetchJobs(),
        this.fetchLogs(),
        this.fetchAnalytics(),
      ]);
    },

    async fetchJobs() {
      try {
        const response = await fetch("/api/jobs");
        if (response.ok) {
          this.jobs = await response.json();
        }
      } catch (error) {
        console.error("Error fetching tasks:", error);
      }
    },

    async fetchTasks() {
      try {
        const response = await fetch("/api/tasks");
        if (response.ok) {
          this.tasks = await response.json();
        }
      } catch (error) {
        console.error("Error fetching tasks:", error);
      }
    },

    async fetchLogs() {
      try {
        const response = await fetch("/api/logs");
        if (response.ok) {
          this.logs = await response.json();
        }
      } catch (error) {
        console.error("Error fetching logs:", error);
      }
    },

    async fetchAnalytics() {
      try {
        const [activity, upcoming, history, distribution] = await Promise.all([
          fetch("/api/analytics/recent-activity").then((r) => r.json()),
          fetch("/api/analytics/upcoming-executions").then((r) => r.json()),
          fetch("/api/analytics/execution-history").then((r) => r.json()),
          fetch("/api/analytics/task-distribution").then((r) => r.json()),
        ]);

        this.analytics = {
          recentActivity: activity || [],
          upcomingExecutions: upcoming || [],
          executionHistory: history || [],
          taskDistribution: distribution || [],
        };
      } catch (error) {
        console.error("Error fetching analytics:", error);
      }
    },
  });
});
