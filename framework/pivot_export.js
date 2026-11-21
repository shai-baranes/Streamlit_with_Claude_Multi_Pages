function computePivot(rowDimension, columnDimension, values, operation) {
  const rows = new Set();
  const columns = new Set();
  const groups = new Map();
  const width = columnDimension.labels.length;

  for (const [index, row] of rowDimension.codes.entries()) {
    const column = columnDimension.codes[index];
    if (row < 0 || column < 0) continue;

    const key = row * width + column;
    let group = groups.get(key);
    if (!group) {
      group = {count: 0, sum: 0, correction: 0, max: -Infinity, missing: false};
      if (operation === "median") group.values = [];
      groups.set(key, group);
    }
    if (values[index] === null) {
      group.missing = true;
      continue;
    }

    const value = Number(values[index]);
    group.count++;
    if (operation === "sum" || operation === "mean") {
      // pandas uses compensated summation for floating point groups.
      const term = value - group.correction;
      const sum = group.sum + term;
      group.correction = (sum - group.sum) - term;
      if (Number.isNaN(group.correction)) group.correction = 0;
      group.sum = sum;
    } else if (operation === "max") {
      group.max = Math.max(group.max, value);
    } else if (operation === "median") {
      group.values.push(value);
    }
  }

  for (const [key, group] of groups) {
    let result;
    switch (operation) {
      case "count": result = group.count; break;
      case "sum": result = group.sum; break;
      case "mean": result = group.sum / group.count; break;
      case "max": result = group.count ? group.max : NaN; break;
      case "median": {
        // The live page passes numpy.median, which propagates missing values.
        if (group.missing) {
          result = NaN;
        } else {
          group.values.sort((a, b) => a - b);
          const middle = Math.floor(group.count / 2);
          result = group.count % 2 ? group.values[middle] :
            (group.values[middle - 1] + group.values[middle]) / 2;
        }
        break;
      }
    }
    if (Number.isNaN(result)) {
      groups.delete(key);
      continue;
    }
    rows.add(Math.floor(key / width));
    columns.add(key % width);
    groups.set(key, result);
  }

  // pandas drops undefined groups before unstacking, then fills missing cells.
  const rowCodes = [...rows].sort((a, b) => a - b);
  const columnCodes = [...columns].sort((a, b) => a - b);
  return {
    rows: rowCodes.map(code => rowDimension.labels[code]),
    columns: columnCodes.map(code => columnDimension.labels[code]),
    cells: rowCodes.map(row => columnCodes.map(column => groups.get(row * width + column) ?? 0)),
  };
}

function renderPivot({parentElement, data}) {
  const output = parentElement.querySelector("[data-pivot-output]");
  const status = parentElement.querySelector("[data-pivot-status]");
  const table = output.querySelector("table");
  const plot = output.querySelector("[data-pivot-plot]");
  const settings = {...data.settings};
  const currency = new Intl.NumberFormat("en-US", {maximumFractionDigits: 0, roundingMode: "halfEven"});
  const units = new Intl.NumberFormat("en-US", {maximumFractionDigits: 0});
  const percent = new Intl.NumberFormat("en-US", {
    minimumFractionDigits: 1, maximumFractionDigits: 1, useGrouping: false, roundingMode: "halfEven",
  });

  function format(value) {
    if (settings.value === "Revenue" || settings.value === "Profit") return "$" + currency.format(value);
    if (settings.value === "Margin_%") return percent.format(value) + "%";
    return units.format(Math.trunc(value) || 0);
  }

  function shade(value, low, high) {
    const colors = data.colors;
    const scaled = Number.isFinite(value) && high > low ? (value - low) / (high - low) : 0;
    return colors[Math.min(colors.length - 1, Math.floor(scaled * colors.length))];
  }

  function renderTable(matrix) {
    let low = Infinity;
    let high = -Infinity;
    for (const row of matrix.cells) {
      for (const value of row) {
        if (!Number.isFinite(value)) continue;
        low = Math.min(low, value);
        high = Math.max(high, value);
      }
    }

    table.replaceChildren();
    const header = table.createTHead().insertRow();
    for (const label of [settings.rows, ...matrix.columns]) {
      const cell = document.createElement("th");
      cell.scope = "col";
      cell.textContent = label;
      header.append(cell);
    }
    const body = table.createTBody();
    for (const [index, values] of matrix.cells.entries()) {
      const row = body.insertRow();
      const label = document.createElement("th");
      label.scope = "row";
      label.textContent = matrix.rows[index];
      row.append(label);
      for (const value of values) {
        const cell = row.insertCell();
        cell.textContent = format(value);
        const color = shade(value, low, high);
        cell.style.backgroundColor = color;
        const [red, green, blue] = color.slice(1).match(/../g).map(hex => {
          const channel = parseInt(hex, 16) / 255;
          return channel <= 0.04045 ? channel / 12.92 : ((channel + 0.055) / 1.055) ** 2.4;
        });
        cell.style.color = 0.2126 * red + 0.7152 * green + 0.0722 * blue < 0.408 ? "#f1f1f1" : "#000";
      }
    }
  }

  function update() {
    if (settings.rows === settings.columns) {
      status.textContent = "⚠️ Rows and Columns must be different dimensions.";
      output.hidden = true;
      return;
    }
    const matrix = computePivot(data.dimensions[settings.rows], data.dimensions[settings.columns],
      data.values[settings.value], settings.operation);
    if (!matrix.rows.length) {
      status.textContent = "No groups for these dimensions and values.";
      output.hidden = true;
      return;
    }
    const description = `${settings.operation}(${settings.value}) — ${settings.rows} × ${settings.columns}`;
    status.textContent = `Pivot: ${description} — ${matrix.rows.length} row groups`;
    output.hidden = false;
    renderTable(matrix);

    // Plotly supports markup in labels. Render dataset values as literal text.
    const plotLabel = label => String(label).replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;").replaceAll(">", "&gt;");
    const x = matrix.columns.map(plotLabel);
    const y = matrix.rows.map(plotLabel);
    Plotly.react(plot, [{
      type: "heatmap", x, y, z: matrix.cells, colorscale: "Viridis",
      texttemplate: "%{z}",
      hovertemplate: `${settings.columns}=%{x}<br>${settings.rows}=%{y}<br>${settings.value}=%{z}<extra></extra>`,
    }], {
      title: {text: `Heatmap: ${description}`, font: {size: 14}},
      xaxis: {title: {text: settings.columns}, type: "category", automargin: true},
      yaxis: {title: {text: settings.rows}, type: "category", autorange: "reversed", automargin: true},
      margin: {t: 65, r: 10, b: 55, l: 55},
      paper_bgcolor: "#fff",
    }, {responsive: true});
  }

  for (const [field, choices] of Object.entries(data.options)) {
    const select = parentElement.querySelector(`[data-${field}]`);
    for (const choice of choices) select.add(new Option(choice, choice));
    select.value = settings[field];
    select.addEventListener("change", () => {
      settings[field] = select.value;
      update();
    });
  }
  update();
}
