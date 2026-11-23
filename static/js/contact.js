// The contact form's proof of work: find a number whose sha256 with the challenge starts
// with enough zero bits. Starts once someone begins to write, so visitors who only look
// don't spend any power on it. Plain JS sha256: crypto.subtle is missing outside https
// and very slow for many small hashes in Firefox and Safari.
(function () {
  var form = document.getElementById('contact-form');
  if (!form || !form.dataset.challenge) return;
  var challenge = form.dataset.challenge + ':';
  var bits = parseInt(form.dataset.difficulty, 10);  // up to 32, only the first word is checked
  var button = form.querySelector('button[type=submit]');
  var nonce = form.querySelector('input[name=nonce]');
  var work = null;

  var K = new Uint32Array([
    0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5, 0x3956c25b, 0x59f111f1, 0x923f82a4, 0xab1c5ed5,
    0xd807aa98, 0x12835b01, 0x243185be, 0x550c7dc3, 0x72be5d74, 0x80deb1fe, 0x9bdc06a7, 0xc19bf174,
    0xe49b69c1, 0xefbe4786, 0x0fc19dc6, 0x240ca1cc, 0x2de92c6f, 0x4a7484aa, 0x5cb0a9dc, 0x76f988da,
    0x983e5152, 0xa831c66d, 0xb00327c8, 0xbf597fc7, 0xc6e00bf3, 0xd5a79147, 0x06ca6351, 0x14292967,
    0x27b70a85, 0x2e1b2138, 0x4d2c6dfc, 0x53380d13, 0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85,
    0xa2bfe8a1, 0xa81a664b, 0xc24b8b70, 0xc76c51a3, 0xd192e819, 0xd6990624, 0xf40e3585, 0x106aa070,
    0x19a4c116, 0x1e376c08, 0x2748774c, 0x34b0bcb5, 0x391c0cb3, 0x4ed8aa4a, 0x5b9cca4f, 0x682e6ff3,
    0x748f82ee, 0x78a5636f, 0x84c87814, 0x8cc70208, 0x90befffa, 0xa4506ceb, 0xbef9a3f7, 0xc67178f2
  ]);
  var m = new Uint32Array(64);

  function rotr(x, n) { return (x >>> n) | (x << (32 - n)); }

  // The first 32 bits of sha256 of an ASCII text
  function firstWord(text) {
    var n = text.length, words = (((n + 8) >> 6) + 1) * 16, w = new Uint32Array(words), i, t;
    for (i = 0; i < n; i++) w[i >> 2] |= text.charCodeAt(i) << (24 - (i & 3) * 8);
    w[n >> 2] |= 0x80 << (24 - (n & 3) * 8);
    w[words - 1] = n * 8;
    var h0 = 0x6a09e667, h1 = 0xbb67ae85, h2 = 0x3c6ef372, h3 = 0xa54ff53a,
        h4 = 0x510e527f, h5 = 0x9b05688c, h6 = 0x1f83d9ab, h7 = 0x5be0cd19;
    for (var block = 0; block < words; block += 16) {
      for (t = 0; t < 16; t++) m[t] = w[block + t];
      for (t = 16; t < 64; t++) {
        var x = m[t - 15], y = m[t - 2];
        m[t] = (m[t - 16] + (rotr(x, 7) ^ rotr(x, 18) ^ (x >>> 3)) + m[t - 7] + (rotr(y, 17) ^ rotr(y, 19) ^ (y >>> 10))) | 0;
      }
      var a = h0, b = h1, c = h2, d = h3, e = h4, f = h5, g = h6, h = h7;
      for (t = 0; t < 64; t++) {
        var t1 = (h + (rotr(e, 6) ^ rotr(e, 11) ^ rotr(e, 25)) + ((e & f) ^ (~e & g)) + K[t] + m[t]) | 0;
        var t2 = ((rotr(a, 2) ^ rotr(a, 13) ^ rotr(a, 22)) + ((a & b) ^ (a & c) ^ (b & c))) | 0;
        h = g; g = f; f = e; e = (d + t1) | 0; d = c; c = b; b = a; a = (t1 + t2) | 0;
      }
      h0 = (h0 + a) | 0; h1 = (h1 + b) | 0; h2 = (h2 + c) | 0; h3 = (h3 + d) | 0;
      h4 = (h4 + e) | 0; h5 = (h5 + f) | 0; h6 = (h6 + g) | 0; h7 = (h7 + h) | 0;
    }
    return h0 >>> 0;
  }

  // In slices, so the page stays responsive while it works
  function solve() {
    return new Promise(function (resolve) {
      var next = 0;
      (function slice() {
        for (var end = next + 20000; next < end; next++) {
          if (firstWord(challenge + next) >>> (32 - bits) === 0) return resolve(String(next));
        }
        setTimeout(slice, 0);
      })();
    });
  }

  function begin() {
    if (!work) work = solve().then(function (found) { nonce.value = found; });
    return work;
  }

  button.disabled = false;
  form.addEventListener('input', begin, { once: true });
  form.addEventListener('submit', function (event) {
    if (nonce.value) return;
    event.preventDefault();
    if (!form.reportValidity()) return;
    button.disabled = true;
    button.querySelector('span').textContent = button.dataset.checking;
    begin().then(function () { form.submit(); });
  });
})();
