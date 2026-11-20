/* 파티클 구체. Sphere.setMode('idle'|'hover'|'analyzing'|'done') */
(function () {
  const cv = document.getElementById('cv'), ctx = cv.getContext('2d');
  let W = 0, H = 0;
  function resize() {
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    W = cv.clientWidth; H = cv.clientHeight;
    cv.width = W * dpr; cv.height = H * dpr;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  }
  window.addEventListener('resize', resize); resize();

  const N = 9000, P = [];
  for (let i = 0; i < N; i++) {
    const u = Math.random() * 2 - 1, th = Math.random() * Math.PI * 2, s = Math.sqrt(1 - u * u);
    const k = Math.random();
    let r, kind;
    if (k < 0.6) { r = 0.96 + Math.random() * 0.06; kind = 0; }
    else if (k < 0.78) { r = Math.cbrt(Math.random()) * 0.94; kind = 1; }
    else { r = 1.08 + Math.pow(Math.random(), 1.7) * 0.8; kind = 2; }
    P.push({ dx: s * Math.cos(th), dy: u, dz: s * Math.sin(th), r, kind,
             a: 0.2 + Math.random() * 0.8, big: Math.random() < 0.07, ph: Math.random() * 6.283 });
  }

  const S = { mode: 'idle', rot: 0, speed: .0018, tSpeed: .0018, scale: 1, tScale: 1, halo: 1, tHalo: 1, mx: 0, my: 0 };
  const modes = {
    idle: { speed: .0018, scale: 1, halo: 1 },
    hover: { speed: .006, scale: 1.07, halo: 1.25 },
    analyzing: { speed: .022, scale: .94, halo: .55 },
    done: { speed: .0012, scale: 1, halo: 1.05 }
  };
  function setMode(m) { S.mode = m; const o = modes[m]; S.tSpeed = o.speed; S.tScale = o.scale; S.tHalo = o.halo; }
  window.addEventListener('mousemove', e => { S.mx = (e.clientX / innerWidth - .5); S.my = (e.clientY / innerHeight - .5); });

  let t = 0;
  function frame() {
    t += 0.016;
    S.speed += (S.tSpeed - S.speed) * .04;
    S.scale += (S.tScale - S.scale) * .05;
    S.halo += (S.tHalo - S.halo) * .03;
    S.rot += S.speed;

    ctx.globalAlpha = 1; ctx.fillStyle = '#000'; ctx.fillRect(0, 0, W, H);
    const R = Math.min(W, H) * .27 * S.scale, cx = W / 2, cy = H / 2;
    const tilt = .32 + S.my * .3, yaw = S.rot + S.mx * .5;
    const cy1 = Math.cos(yaw), sy1 = Math.sin(yaw), cx1 = Math.cos(tilt), sx1 = Math.sin(tilt);
    const pulse = S.mode === 'analyzing' ? Math.sin(t * 6) * .015 : 0;
    const unit = Math.max(.8, Math.min(1.4, R / 190));

    const g = ctx.createRadialGradient(cx, cy, R * .82, cx, cy, R * 1.25);
    g.addColorStop(0, 'rgba(255,255,255,0)');
    g.addColorStop(.45, 'rgba(255,255,255,.07)');
    g.addColorStop(1, 'rgba(255,255,255,0)');
    ctx.fillStyle = g; ctx.fillRect(cx - R * 1.3, cy - R * 1.3, R * 2.6, R * 2.6);
    ctx.globalCompositeOperation = 'lighter';
    ctx.fillStyle = '#fff';
    for (let i = 0; i < N; i++) {
      const p = P[i];
      let r = p.r;
      if (p.kind === 2) r = 1 + (p.r - 1) * S.halo + Math.sin(t * .8 + p.ph) * .02;
      else if (p.kind === 0) r += pulse + Math.sin(t * 1.3 + p.ph) * .004;
      let x = p.dx * r, y = p.dy * r, z = p.dz * r;
      if (p.kind === 2 && S.mode === 'analyzing') {
        const a = t * 1.4 * (1.6 - (p.r - 1));
        const ca = Math.cos(a), sa = Math.sin(a);
        const nx = x * ca - z * sa; z = x * sa + z * ca; x = nx;
      }
      const x1 = x * cy1 - z * sy1, z1 = x * sy1 + z * cy1;
      const y1 = y * cx1 - z1 * sx1, z2 = y * sx1 + z1 * cx1;
      const f = 4 / (4 - z2);
      const px = cx + x1 * R * f, py = cy + y1 * R * f;
      const depth = (z2 + 1.8) / 3.6;
      let al = p.a * (.35 + .65 * depth);
      if (p.kind === 0) al = Math.min(1, al * 1.25);
      if (p.kind === 1) al *= .35;
      if (p.kind === 2) al *= .9 * Math.max(0, 1 - (p.r - 1.08) / .95);
      ctx.globalAlpha = al;
      const sz = (p.big ? 2.4 : (p.kind === 2 ? 1.9 : 1.5)) * unit;
      ctx.fillRect(px, py, sz * f, sz * f);
    }
    ctx.globalCompositeOperation = 'source-over';
    requestAnimationFrame(frame);
  }
  frame();
  window.Sphere = { setMode };
})();
