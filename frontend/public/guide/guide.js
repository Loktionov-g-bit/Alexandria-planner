// click a screenshot to see it full size
  const lb = document.getElementById('lb'), lbImg = lb.querySelector('img')
  document.querySelectorAll('figure.shot .frame').forEach((f) => f.addEventListener('click', () => {
    const img = f.querySelector('img'); lbImg.src = img.src; lbImg.alt = img.alt; lb.classList.add('open')
  }))
  lb.addEventListener('click', () => lb.classList.remove('open'))
  document.addEventListener('keydown', (e) => { if (e.key === 'Escape') lb.classList.remove('open') })
  // highlight the current section in the table of contents
  const links = new Map([...document.querySelectorAll('.toc a[href^="#"]')].map((a) => [a.getAttribute('href').slice(1), a]))
  const io = new IntersectionObserver((entries) => entries.forEach((e) => {
    if (!e.isIntersecting) return
    links.forEach((a) => a.classList.remove('on')); links.get(e.target.id)?.classList.add('on')
  }), { rootMargin: '-30% 0px -60% 0px' })
  document.querySelectorAll('section[id]').forEach((s) => io.observe(s))
