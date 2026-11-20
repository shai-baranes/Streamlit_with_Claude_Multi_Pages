function renderTrajectory({parentElement: root, data}) {
  const select = name => root.querySelector(`.trajectory-${name}`);
  const control = name => root.querySelector(`[data-control="${name}"]`);
  const zoom = control("zoom");
  const marker = control("marker");
  const duration = control("duration");
  const showPoints = control("points");
  const stepControl = control("step");
  const play = control("play");
  const pause = control("pause");
  const map = select("map");
  const world = select("world");
  const traveled = select("traveled");
  const sampleLayer = select("samples");
  const current = select("current");
  const timeLabel = select("time");
  const position = select("position");

  function project(lon, lat) {
    const radians = Math.PI / 180;
    const latitude = Math.max(-85.0511, Math.min(85.0511, lat)) * radians;
    return [lon, -Math.asinh(Math.tan(latitude)) / radians];
  }

  const route = data.route.map(([, lat, lon]) => project(lon, lat));
  const last = route.length - 1;
  const west = Math.min(...route.map(([x]) => x));
  const east = Math.max(...route.map(([x]) => x));
  const north = Math.min(...route.map(([, y]) => y));
  const south = Math.max(...route.map(([, y]) => y));
  let centerX = (west + east) / 2;
  let centerY = (north + south) / 2;
  let width = 1;
  let height = 1;
  let scale = 1;
  let step = 0;
  let timer = null;
  let drag = null;

  zoom.value = data.zoom;
  marker.value = data.markerSize;
  duration.value = data.frameDuration;
  showPoints.checked = data.showPoints;
  stepControl.max = last;
  select("credit").textContent = data.coast.source;
  const [minLon, minLat, maxLon, maxLat] = data.coast.bounds;
  const [left, top] = project(minLon, maxLat);
  const [right, bottom] = project(maxLon, minLat);
  const water = select("water");
  water.setAttribute("x", left);
  water.setAttribute("y", top);
  water.setAttribute("width", right - left);
  water.setAttribute("height", bottom - top);
  const paths = data.coast.rings.map(ring => "M " + ring.map(point => project(...point).join(",")).join(" L ") + " Z");
  select("land").setAttribute("d", paths.join(" "));
  select("route").setAttribute("points", route.join(" "));

  function pointDetails(index) {
    const [time, lat, lon] = data.route[index];
    return `Time ${time} · Lat ${lat.toFixed(5)} · Lon ${lon.toFixed(5)}`;
  }

  const samples = route.map((_, index) => {
    const circle = document.createElementNS(map.namespaceURI, "circle");
    const title = document.createElementNS(map.namespaceURI, "title");
    circle.setAttribute("r", 3.5);
    title.textContent = pointDetails(index);
    circle.append(title);
    sampleLayer.append(circle);
    return circle;
  });

  function setOutput(input, text) {
    input.labels[0].querySelector(".trajectory-value").textContent = text;
    input.setAttribute("aria-valuetext", text);
  }

  function place(element, [x, y]) {
    element.setAttribute("cx", (x - centerX) * scale + width / 2);
    element.setAttribute("cy", (y - centerY) * scale + height / 2);
  }

  function drawCurrent() {
    place(current, route[step]);
    const x = Number(current.getAttribute("cx"));
    const y = Number(current.getAttribute("cy"));
    const labelOnLeft = x > width - 65;
    timeLabel.setAttribute("x", x + (labelOnLeft ? -1 : 1) * (marker.valueAsNumber / 2 + 5));
    timeLabel.setAttribute("y", y < 22 ? y + 18 : y - 9);
    timeLabel.setAttribute("text-anchor", labelOnLeft ? "end" : "start");
  }

  function drawMap() {
    // Level nine fits the route in the available viewport. Each two steps double the scale.
    scale = Math.min(width / Math.max(1.6 * (east - west), 0.2),
                     height / Math.max(1.35 * (south - north), 0.2)) * 2 ** ((zoom.valueAsNumber - 9) / 2);
    world.setAttribute("transform",
      `translate(${width / 2} ${height / 2}) scale(${scale}) translate(${-centerX} ${-centerY})`);
    samples.forEach((circle, index) => place(circle, route[index]));
    drawCurrent();
  }

  function drawStep() {
    stepControl.value = step;
    setOutput(stepControl, `${step + 1} / ${route.length}`);
    traveled.setAttribute("points", route.slice(0, step + 1).join(" "));
    current.querySelector("title").textContent = pointDetails(step);
    timeLabel.textContent = `T=${data.route[step][0]}`;
    position.textContent = pointDetails(step);
    drawCurrent();
  }

  function stopPlayback() {
    clearTimeout(timer);
    timer = null;
    play.disabled = false;
    pause.disabled = true;
  }

  function scheduleFrame() {
    timer = setTimeout(() => {
      step++;
      drawStep();
      if (step === last) stopPlayback();
      else scheduleFrame();
    }, duration.valueAsNumber);
  }

  play.onclick = () => {
    if (step === last) {
      step = 0;
      drawStep();
    }
    if (!last) return;
    play.disabled = true;
    pause.disabled = false;
    scheduleFrame();
  };
  pause.onclick = stopPlayback;
  stepControl.oninput = () => {
    stopPlayback();
    step = stepControl.valueAsNumber;
    drawStep();
  };
  duration.oninput = () => {
    setOutput(duration, duration.value);
    if (timer !== null) {
      clearTimeout(timer);
      scheduleFrame();
    }
  };
  marker.oninput = () => {
    setOutput(marker, marker.value);
    current.setAttribute("r", marker.valueAsNumber / 2);
    drawCurrent();
  };
  showPoints.onchange = () => sampleLayer.style.display = showPoints.checked ? "" : "none";
  zoom.oninput = () => {
    setOutput(zoom, zoom.value);
    drawMap();
  };

  function pan(dx, dy) {
    centerX -= dx / scale;
    centerY -= dy / scale;
    drawMap();
  }

  function changeZoom(direction) {
    zoom.value = zoom.valueAsNumber + direction;
    zoom.oninput();
  }

  map.addEventListener("wheel", event => {
    event.preventDefault();
    if (event.deltaY) changeZoom(-Math.sign(event.deltaY));
  }, {passive: false});
  map.addEventListener("keydown", event => {
    const offsets = {ArrowLeft: [48, 0], ArrowRight: [-48, 0], ArrowUp: [0, 48], ArrowDown: [0, -48]};
    if (Object.hasOwn(offsets, event.key)) pan(...offsets[event.key]);
    else if (event.key === "+" || event.key === "=") changeZoom(1);
    else if (event.key === "-") changeZoom(-1);
    else return;
    event.preventDefault();
  });
  map.addEventListener("pointerdown", event => {
    if (drag || event.button !== 0) return;
    drag = {id: event.pointerId, x: event.clientX, y: event.clientY};
    map.setPointerCapture(event.pointerId);
  });
  map.addEventListener("pointermove", event => {
    if (drag?.id !== event.pointerId) return;
    pan(event.clientX - drag.x, event.clientY - drag.y);
    drag.x = event.clientX;
    drag.y = event.clientY;
  });
  map.addEventListener("lostpointercapture", () => { drag = null; });

  new ResizeObserver(() => {
    width = map.clientWidth;
    height = map.clientHeight;
    map.setAttribute("viewBox", `0 0 ${width} ${height}`);
    drawMap();
  }).observe(map);

  zoom.oninput();
  marker.oninput();
  duration.oninput();
  showPoints.onchange();
  stopPlayback();
  drawStep();
}
