(() => {
  const source = document.getElementById("overview-data");
  if (!source || !window.echarts) return;
  const data = JSON.parse(source.textContent);
  const common = { animation: false, textStyle: { color: "#57606a" } };

  function render(id, option) {
    const element = document.getElementById(id);
    if (!element) return;
    const chart = window.echarts.init(element, null, { renderer: "svg" });
    chart.setOption({ ...common, ...option });
    window.addEventListener("resize", () => chart.resize());
  }

  const responseBins = [0, 0, 0, 0, 0];
  data.charts.response_hours.forEach((hours) => {
    const index = hours <= 12 ? 0 : hours <= 24 ? 1 : hours <= 72 ? 2 : hours <= 168 ? 3 : 4;
    responseBins[index] += 1;
  });
  render("response-chart", {
    tooltip: { trigger: "axis" },
    grid: { top: 15, right: 10, bottom: 30, left: 35 },
    xAxis: { type: "category", data: ["≤12h", "≤24h", "≤72h", "≤7d", ">7d"] },
    yAxis: { type: "value", minInterval: 1 },
    series: [{ type: "bar", data: responseBins, itemStyle: { color: "#0969da" } }]
  });
  render("backlog-chart", {
    tooltip: { trigger: "axis" },
    grid: { top: 15, right: 10, bottom: 30, left: 35 },
    xAxis: { type: "category", data: ["0–30", "31–90", "91–180", "180+"] },
    yAxis: { type: "value", minInterval: 1 },
    series: [{ type: "bar", data: data.charts.backlog_age, itemStyle: { color: "#9a6700" } }]
  });
  render("collaboration-chart", {
    tooltip: { trigger: "axis" },
    grid: { top: 15, right: 10, bottom: 30, left: 35 },
    xAxis: { type: "category", data: ["Issues", "关联 PR", "合并 PR"] },
    yAxis: { type: "value", minInterval: 1 },
    series: [{ type: "bar", data: data.charts.collaboration, itemStyle: { color: "#1a7f37" } }]
  });
})();

