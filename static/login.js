const form = document.getElementById("login-form");
const errorEl = document.getElementById("error");

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  errorEl.textContent = "";

  const username = document.getElementById("username").value.trim();
  const password = document.getElementById("password").value;

  try {
    const resp = await fetch("/api/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username, password }),
    });
    const data = await resp.json();

    if (!resp.ok || !data.ok) {
      errorEl.textContent = data.error || "登录失败";
      return;
    }

    window.location.href = "/chat";
  } catch (err) {
    errorEl.textContent = `请求失败：${err}`;
  }
});
