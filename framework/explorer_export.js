function explorerNumber(value) {
  if (value === null) return null;
  if (value === "inf") return Infinity;
  if (value === "-inf") return -Infinity;
  return Number(value);
}

function compareExplorerValues(a, b) {
  if (a === b) return 0;
  if (a === null) return 1;
  if (b === null) return -1;
  // CSV columns with mixed scalar types follow pandas' numeric-before-text order.
  if (typeof a === "string" && typeof b !== "string") return 1;
  if (typeof b === "string" && typeof a !== "string") return -1;
  return a < b ? -1 : a > b ? 1 : 0;
}

function explorerGroups(data, fields, column, operation) {
  const {schema, original, preview} = data;
  const metric = schema[column];
  const groupColumns = fields.map(index => original[index]);
  const groups = new Map();

  original[column].forEach((value, index) => {
    const keys = groupColumns.map(values => values[index]);
    const id = JSON.stringify(keys);
    let group = groups.get(id);
    if (!group) {
      group = {keys, count: 0, sum: 0, compensation: 0, exact: 0n, value: null};
      if (operation === "median") group.samples = [];
      groups.set(id, group);
    }
    if (value === null) return;
    group.count++;
    switch (operation) {
      case "sum":
      case "mean": {
        if (metric.integer) {
          group.exact += BigInt(value);
          break;
        }
        // Compensated summation follows pandas for floating point groups.
        const adjusted = explorerNumber(value) - group.compensation;
        const total = group.sum + adjusted;
        group.compensation = Number.isFinite(total) ? (total - group.sum) - adjusted : 0;
        group.sum = total;
        break;
      }
      case "min":
      case "max": {
        const numeric = metric.integer ? BigInt(value) : explorerNumber(value);
        if (group.value === null || (operation === "min" ? numeric < group.value : numeric > group.value)) {
          group.value = numeric;
        }
        break;
      }
      case "median":
        group.samples.push(explorerNumber(value));
        break;
    }
  });

  function result(group) {
    switch (operation) {
      case "count": return group.count;
      case "sum":
        if (!metric.integer) return group.sum;
        return metric.unsigned ? BigInt.asUintN(64, group.exact) : BigInt.asIntN(64, group.exact);
      case "mean":
        return group.count ? (metric.integer ? Number(group.exact) : group.sum) / group.count : null;
      case "median": {
        if (!group.count) return null;
        group.samples.sort(compareExplorerValues);
        const middle = Math.floor(group.count / 2);
        return group.count % 2 ? group.samples[middle] : (group.samples[middle - 1] + group.samples[middle]) / 2;
      }
      default: return group.value;
    }
  }
  const sorted = [...groups.values()].sort((a, b) => {
    for (const [position, field] of fields.entries()) {
      const x = a.keys[position], y = b.keys[position];
      const integer = schema[field].integer && x !== null && y !== null;
      const numeric = schema[field].numeric && x !== null && y !== null;
      const order = integer ? compareExplorerValues(BigInt(x), BigInt(y))
        : numeric ? compareExplorerValues(explorerNumber(x), explorerNumber(y)) : compareExplorerValues(x, y);
      if (order) return order;
    }
    return 0;
  });
  return {
    length: sorted.length,
    rows: sorted.slice(0, preview).map(group => [...group.keys, result(group)]),
  };
}

function selectExplorerRows(values, count, limit, bounds) {
  const rows = [];
  for (let index = 0; index < count; index++) {
    if (!values || (values[index] !== null &&
        (!bounds || (values[index] >= bounds[0] && values[index] <= bounds[1])))) rows.push(index);
  }
  if (rows.length <= limit) return {rows, reduced: false};
  if (limit === 1) return {rows: [rows[0]], reduced: true};
  const stride = (rows.length - 1) / (limit - 1);
  return {
    rows: Array.from({length: limit}, (_, i) => rows[i === limit - 1 ? rows.length - 1 : Math.floor(i * stride)]),
    reduced: true,
  };
}

function renderExplorer({parentElement: root, data}) {
  const {schema, original, converted, settings, points} = data;
  const control = name => root.querySelector(`[data-${name}]`);
  if (!schema.some(column => column.numeric)) {
    control("no-numeric").hidden = false;
    return;
  }
  control("explorer-controls").hidden = false;

  const columns = schema.map(({name}, index) => [index, name]);
  const numeric = columns.filter(([index]) => schema[index].numeric);
  const asIndexes = names => names.map(name => schema.findIndex(column => column.name === name));
  const groupFields = asIndexes(settings.group);
  const yFields = asIndexes(settings.y);
  const ranges = new Map();
  const plot = control("chart");
  const rangePanel = control("range");
  const low = control("low");
  const high = control("high");
  const metric = control("metric");
  const operation = control("operation");
  const x = control("x");
  const interpretation = control("interpretation");
  const kind = control("kind");

  function element(parent, tag, text) {
    const child = document.createElement(tag);
    if (text !== undefined) child.textContent = text;
    parent.append(child);
    return child;
  }

  function options(select, values, selected) {
    select.replaceChildren(...values.map(([value, label]) => new Option(label, value)));
    select.value = selected;
  }

  function fieldPicker(host, title, choices, fields, onChange) {
    const add = element(element(host, "label", title), "select");
    const list = element(host, "ol");
    list.className = "explorer-fields";
    function paint() {
      list.replaceChildren();
      options(add, [["", "Choose a field"], ...choices.filter(([index]) => !fields.includes(index))], "");
      fields.forEach((field, position) => {
        const name = schema[field].name;
        const item = element(list, "li", name);
        for (const [action, step] of [["Move up", -1], ["Move down", 1], ["Remove", 0]]) {
          const button = element(item, "button", action);
          const next = position + step;
          button.type = "button";
          button.setAttribute("aria-label", `${action} ${name}`);
          button.disabled = next < 0 || next >= fields.length;
          button.onclick = () => {
            if (step) [fields[next], fields[position]] = [fields[position], fields[next]];
            else fields.splice(position, 1);
            paint();
            onChange();
          };
        }
      });
    }
    add.onchange = () => {
      if (!add.value) return;
      fields.push(Number(add.value));
      paint();
      onChange();
    };
    paint();
  }

  function renderGroups() {
    const results = control("results");
    const message = control("group-message");
    results.replaceChildren();
    message.textContent = "";
    const valueField = Number(metric.value);
    if (groupFields.includes(valueField)) {
      message.textContent = "Choose a value field that is not also a grouping field.";
      return;
    }
    if (!groupFields.length) return;
    const {rows, length} = explorerGroups(data, groupFields, valueField, operation.value);
    const table = element(results, "table");
    const head = element(table.createTHead(), "tr");
    const body = table.createTBody();
    const headings = [...groupFields, valueField];
    const headers = headings.map(() => element(head, "th"));
    function paint() {
      body.replaceChildren();
      for (const row of rows) {
        const line = body.insertRow();
        for (const value of row) element(line, "td", value === null || Number.isNaN(value) ? "" : String(value));
      }
    }
    headers.forEach((header, position) => {
      const field = schema[headings[position]];
      const button = element(header, "button", field.name);
      button.type = "button";
      button.onclick = () => {
        const ascending = header.getAttribute("aria-sort") !== "ascending";
        for (const th of headers) th.removeAttribute("aria-sort");
        header.setAttribute("aria-sort", ascending ? "ascending" : "descending");
        rows.sort((a, b) => {
          const left = a[position], right = b[position];
          if (left == null || Number.isNaN(left)) return right == null || Number.isNaN(right) ? 0 : 1;
          if (right == null || Number.isNaN(right)) return -1;
          const compare = position < groupFields.length && field.integer
            ? compareExplorerValues(BigInt(left), BigInt(right))
            : field.numeric && typeof left !== "bigint" ? compareExplorerValues(explorerNumber(left), explorerNumber(right))
            : compareExplorerValues(left, right);
          return ascending ? compare : -compare;
        });
        paint();
      };
    });
    if (length > rows.length) message.textContent = `Showing ${rows.length.toLocaleString()} of ${length.toLocaleString()} groups.`;
    paint();
  }

  function plotText(value) {
    return typeof value === "string" ? value.replace(/[&<>]/g, char => ({"&": "&amp;", "<": "&lt;", ">": "&gt;"}[char])) : value;
  }

  function rangeDate(value) {
    const parts = value.trim().match(/^(\d{4}-\d\d-\d\d)(?:[T ](\d\d):(\d\d)(?::(\d\d)(?:\.(\d{1,9}))?)?)?$/);
    if (!parts) return null;
    const [, date, hour = "00", minute = "00", second = "00", fraction = ""] = parts;
    const prefix = `${date}T${hour}:${minute}:${second}`;
    const instant = new Date(prefix + "Z");
    if (!Number.isFinite(instant.valueOf()) || instant.toISOString().slice(0, 19) !== prefix) return null;
    return prefix + "." + fraction.padEnd(9, "0");
  }

  const rangeKey = () => `${x.value}:${interpretation.value}`;
  let chartData;
  function bindX() {
    const field = Number(x.value);
    const mode = interpretation.value;
    const values = mode === "Original" ? original[field] : converted[field][mode] ?? original[field];
    const comparable = mode === "Numeric" ? values.map(explorerNumber) : values;
    let min = null, max = null, invalid = false;
    if (mode !== "Original") {
      for (const value of comparable) {
        if (value === null) { invalid = true; continue; }
        if (min === null || value < min) min = value;
        if (max === null || value > max) max = value;
      }
    }
    const finite = mode !== "Numeric" || Number.isFinite(min) && Number.isFinite(max);
    const extent = finite && min !== null && min < max ? [min, max] : null;
    chartData = {field, mode, comparable, invalid, extent};
    rangePanel.hidden = !extent;
    high.setCustomValidity("");
    if (extent) {
      const datetime = mode === "Datetime";
      low.type = high.type = datetime ? "text" : "number";
      low.step = high.step = "any";
      control("range-note").textContent = datetime
        ? "Enter YYYY-MM-DD or an ISO date and time. Times with a source timezone use UTC."
        : `Available range ${min} to ${max}`;
      [low.value, high.value] = ranges.get(rangeKey()) ?? extent;
    }
    renderChart();
  }

  function renderChart() {
    const {field, mode, comparable, invalid, extent} = chartData;
    const bounds = extent && (ranges.get(rangeKey()) ?? extent);
    const {rows, reduced} = selectExplorerRows(mode !== "Original" && comparable, comparable.length, points, bounds);
    const messages = [];
    if (invalid) messages.push("Rows with invalid X values are excluded from the chart.");
    if (reduced) messages.push(`Chart reduced deterministically to ${points.toLocaleString()} points per trace. Aggregates use all matching rows.`);
    if (!yFields.length) messages.push("Select at least one numeric Y field to show a chart.");
    control("chart-message").textContent = messages.join(" ");
    if (!yFields.length) {
      if (plot.data) Plotly.purge(plot);
      return;
    }
    const axisType = mode === "Datetime" || mode === "Original" && schema[field].date ? "date"
      : mode === "Numeric" || schema[field].numeric ? "linear" : "category";
    const xs = rows.map(index => {
      const value = comparable[index];
      return axisType === "linear" ? explorerNumber(value) : axisType === "category" ? plotText(value) : value;
    });
    const traces = yFields.map(series => ({
      type: "scatter",
      mode: kind.value === "Line" ? "lines" : "markers",
      name: plotText(schema[series].name),
      x: xs,
      y: rows.map(index => series === field && mode !== "Original"
        ? comparable[index] : explorerNumber(original[series][index])),
    }));
    Plotly.react(plot, traces, {
      margin: {t: 20, r: 24, b: 70, l: 72},
      xaxis: {type: axisType, title: {text: plotText(schema[field].name)}},
      yaxis: {title: {text: yFields.length === 1 ? plotText(schema[yFields[0]].name) : "value"}},
      showlegend: traces.length > 1,
    }, {responsive: true, displaylogo: false});
  }

  function changeRange() {
    const read = chartData.mode === "Datetime" ? rangeDate
      : value => value.trim() === "" ? null : Number(value);
    const bounds = [read(low.value), read(high.value)];
    if (bounds.some(value => value === null || typeof value === "number" && !Number.isFinite(value))
        || bounds[0] > bounds[1]) {
      high.setCustomValidity("Enter a valid range with the minimum at or below the maximum.");
      high.reportValidity();
      return;
    }
    high.setCustomValidity("");
    ranges.set(rangeKey(), bounds);
    renderChart();
  }

  options(metric, numeric, asIndexes([settings.metric])[0]);
  options(operation, ["sum", "mean", "count", "min", "max", "median"].map(value => [value, value]), settings.operation);
  options(x, columns, asIndexes([settings.x])[0]);
  options(interpretation, ["Original", "Numeric", "Datetime"].map(value => [value, value]), settings.xtype);
  options(kind, [["Line", "Line"], ["Scatter", "Scatter"]], settings.kind);
  if (settings.bounds) ranges.set(rangeKey(), settings.bounds);
  fieldPicker(control("group"), "Group by", columns, groupFields, renderGroups);
  fieldPicker(control("y"), "Trend - Y fields", numeric, yFields, renderChart);
  metric.onchange = operation.onchange = renderGroups;
  x.onchange = interpretation.onchange = bindX;
  kind.onchange = renderChart;
  low.onchange = high.onchange = changeRange;
  control("reset-range").onclick = () => {
    ranges.delete(rangeKey());
    bindX();
  };
  renderGroups();
  bindX();
}
