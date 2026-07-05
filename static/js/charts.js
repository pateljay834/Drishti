/* DRISHTI — charts.js  (Chart.js helper factories) */

Chart.defaults.color = "#8B9FC7";
Chart.defaults.borderColor = "#1A2240";
Chart.defaults.font.family = "Inter, system-ui, sans-serif";

function buildLineChart(ctx, labels, data, color = "#FF6B35", label = "") {
  return new Chart(ctx, {
    type: "line",
    data: {
      labels,
      datasets: [{
        label,
        data,
        borderColor: color,
        borderWidth: 2,
        pointRadius: 0,
        pointHoverRadius: 4,
        tension: 0.3,
        fill: true,
        backgroundColor: (ctx2) => {
          const gradient = ctx2.chart.ctx.createLinearGradient(0, 0, 0, ctx2.chart.height);
          gradient.addColorStop(0, color + "33");
          gradient.addColorStop(1, color + "00");
          return gradient;
        }
      }]
    },
    options: {
      responsive: true,
      animation: { duration: 400 },
      interaction: { intersect: false, mode: "index" },
      plugins: {
        legend: { display: false },
        tooltip: {
          backgroundColor: "#0F1628",
          borderColor: "#1A2240",
          borderWidth: 1,
          titleColor: "#F0F4FF",
          bodyColor: "#8B9FC7",
          padding: 10,
          displayColors: false,
        }
      },
      scales: {
        x: {
          grid: { color: "#1A2240" },
          ticks: {
            maxTicksLimit: 8, maxRotation: 0,
            font: { family: "JetBrains Mono", size: 10 }
          }
        },
        y: {
          grid: { color: "#1A2240" },
          ticks: {
            font: { family: "JetBrains Mono", size: 10 },
            callback: v => v >= 1000 ? v.toLocaleString("en-IN") : v
          },
          position: "right"
        }
      }
    }
  });
}

function buildBarChart(ctx, labels, data, color = "#FF6B35", label = "") {
  return new Chart(ctx, {
    type: "bar",
    data: {
      labels,
      datasets: [{
        label,
        data,
        backgroundColor: data.map(v => (v >= 0 ? color + "CC" : "#EF4444CC")),
        borderColor: data.map(v => (v >= 0 ? color : "#EF4444")),
        borderWidth: 1,
        borderRadius: 4,
      }]
    },
    options: {
      responsive: true,
      animation: { duration: 400 },
      plugins: {
        legend: { display: false },
        tooltip: {
          backgroundColor: "#0F1628",
          borderColor: "#1A2240",
          borderWidth: 1,
          titleColor: "#F0F4FF",
          bodyColor: "#8B9FC7",
          padding: 10,
          displayColors: false,
          callbacks: {
            label: ctx2 => `${ctx2.raw?.toFixed(2) ?? "–"}%`
          }
        }
      },
      scales: {
        x: { grid: { display: false }, ticks: { font: { family: "JetBrains Mono", size: 10 } } },
        y: {
          grid: { color: "#1A2240" },
          ticks: {
            font: { family: "JetBrains Mono", size: 10 },
            callback: v => v + "%"
          }
        }
      }
    }
  });
}
