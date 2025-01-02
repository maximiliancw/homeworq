document.addEventListener("alpine:init", () => {
  Alpine.store("data", {
    search: "",
    tasks: [],
    jobs: { items: [] },
    logs: { items: [] },
    analytics: {
      recentActivity: [],
      upcomingExecutions: [],
      executionHistory: [],
      taskDistribution: [],
    },
    metrics: {
      totalTasks: 0,
      activeJobs: 0,
      totalExecutions: 0,
    },
    health: {
      healthy: false,
      timestamp: null,
    },
    async fetchAll() {
      await Promise.all([
        this.fetchTasks(),
        this.fetchJobs(),
        this.fetchLogs(),
        this.fetchAnalytics(),
      ]);
    },
    async fetchTasks() {
      try {
        const response = await fetch("/api/tasks");
        if (response.ok) {
          this.tasks = await response.json();
          this.metrics.totalTasks = this.tasks.length;
        }
      } catch (error) {
        console.error("Error fetching tasks:", error);
      }
    },
    async fetchJobs() {
      try {
        const response = await fetch("/api/jobs");
        if (response.ok) {
          this.jobs = await response.json();
          this.metrics.activeJobs = this.jobs.items.length;
        }
      } catch (error) {
        console.error("Error fetching jobs:", error);
      }
    },
    async fetchLogs() {
      try {
        const response = await fetch("/api/logs");
        if (response.ok) {
          this.logs = await response.json();
          this.metrics.totalExecutions = this.logs.items.length;
        }
      } catch (error) {
        console.error("Error fetching logs:", error);
      }
    },
    async fetchAnalytics() {
      try {
        const [activity, upcoming, history, distribution] = await Promise.all([
          fetch("/api/analytics/recent-activity")
            .then((r) => r.json())
            .catch(() => []),
          fetch("/api/analytics/upcoming-executions")
            .then((r) => r.json())
            .catch(() => []),
          fetch("/api/analytics/execution-history")
            .then((r) => r.json())
            .catch(() => []),
          fetch("/api/analytics/task-distribution")
            .then((r) => r.json())
            .catch(() => []),
        ]);

        this.analytics = {
          recentActivity: activity || [],
          upcomingExecutions: upcoming || [],
          executionHistory: history || [],
          taskDistribution: distribution || [],
        };
      } catch (error) {
        console.error("Error fetching analytics:", error);
        // Maintain default empty arrays on error
      }
    },
    async checkHealth() {
      try {
        const response = await fetch("/api/health");
        if (response.ok) {
          this.health = await response.json();
        }
      } catch (error) {
        console.error("Error checking health:", error);
        this.health.healthy = false;
        showToast("API connection failed", "error");
      }
    },
  });
});
