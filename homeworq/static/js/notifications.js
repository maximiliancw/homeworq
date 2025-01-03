class NotificationManager {
  constructor() {
    this.notifications = {};
    this.nextNotificationId = 1;
    this.expandedGroups = new Set();
    this.groupTimeouts = {};
  }

  showNotification(message, type = "info", group = null) {
    const id = this.nextNotificationId++;
    const notification = {
      message,
      type,
      group,
      timestamp: Date.now(),
      hidden: false,
    };

    if (group) {
      this.resetGroupTimeout(group);

      Object.entries(this.notifications).forEach(
        ([existingId, existingNotification]) => {
          if (existingNotification.group === group) {
            existingNotification.hidden = true;
          }
        }
      );
    } else {
      setTimeout(() => this.removeNotification(id), 3000);
    }

    this.notifications[id] = notification;
  }

  resetGroupTimeout(group) {
    if (this.groupTimeouts[group]) {
      clearTimeout(this.groupTimeouts[group]);
    }

    this.groupTimeouts[group] = setTimeout(() => {
      this.removeGroupNotifications(group);
    }, 5000);
  }

  toggleGroup(group) {
    if (this.expandedGroups.has(group)) {
      this.expandedGroups.delete(group);
      Object.values(this.notifications).forEach((notification) => {
        if (
          notification.group === group &&
          notification !== this.getLatestGroupNotification(group)
        ) {
          notification.hidden = true;
        }
      });
    } else {
      this.expandedGroups.add(group);
      Object.values(this.notifications).forEach((notification) => {
        if (notification.group === group) {
          notification.hidden = false;
        }
      });
      this.resetGroupTimeout(group);
    }
  }

  removeNotification(id) {
    const notification = this.notifications[id];
    if (!notification) return;

    const notificationEl = document.querySelector(
      `[data-notification-id="${id}"]`
    );

    // If this is a grouped notification
    if (notification.group) {
      const latestGroupNotification = this.getLatestGroupNotification(
        notification.group
      );

      // If this is the latest notification in the group, remove the whole group
      if (notification === latestGroupNotification) {
        this.removeGroupNotifications(notification.group);
        return;
      }
    }

    // Handle single notification removal
    if (notificationEl) {
      notificationEl.classList.add("notification-exit");
      notificationEl.addEventListener("animationend", () => {
        delete this.notifications[id];
      });
    } else {
      delete this.notifications[id];
    }
  }

  removeGroupNotifications(group) {
    Object.entries(this.notifications).forEach(([id, notification]) => {
      if (notification.group === group) {
        const notificationEl = document.querySelector(
          `[data-notification-id="${id}"]`
        );
        if (notificationEl) {
          notificationEl.classList.add("notification-exit");
          notificationEl.addEventListener("animationend", () => {
            delete this.notifications[id];
          });
        } else {
          delete this.notifications[id];
        }
      }
    });
    delete this.groupTimeouts[group];
  }

  getLatestGroupNotification(group) {
    return Object.values(this.notifications)
      .filter((notification) => notification.group === group)
      .sort((a, b) => b.timestamp - a.timestamp)[0];
  }

  getGroupCount(group) {
    return Object.values(this.notifications).filter(
      (notification) => notification.group === group
    ).length;
  }
}
