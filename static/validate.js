// Browser-side checks. The server checks the same rules again (R8).
(function () {
  const rules = {
    register(f) {
      const e = {};
      if (!f.name.value.trim()) e.name = "Name is required";
      if (!f.email.value.trim()) e.email = "Email is required";
      if (!f.password.value) e.password = "Password is required";
      if (!f.confirm_password.value) e.confirm_password = "Confirm password is required";
      else if (f.password.value && f.password.value !== f.confirm_password.value)
        e.confirm_password = "Passwords do not match";
      return e;
    },
    login(f) {
      const e = {};
      if (!f.email.value.trim()) e.email = "Email is required";
      if (!f.password.value) e.password = "Password is required";
      return e;
    },
    todo(f) {
      const e = {};
      const t = f.title.value.trim();
      if (!t) e.title = "Title is required";
      else if (t.length > 200) e.title = "Title is too long";
      return e;
    },
  };

  document.querySelectorAll("form[data-validate]").forEach((form) => {
    form.addEventListener("submit", (ev) => {
      const errors = rules[form.dataset.validate](form.elements);
      form.querySelectorAll(".error[data-for]").forEach((p) => {
        const name = p.dataset.for;
        p.textContent = errors[name] || "";
        const input = form.elements[name];
        if (input) input.classList.toggle("invalid", !!errors[name]);
      });
      const alert = document.querySelector(".alert");
      if (alert && Object.keys(errors).length) alert.remove();
      if (Object.keys(errors).length) {
        ev.preventDefault();
        const first = form.querySelector(".invalid");
        if (first) first.focus();
      }
    });
  });
})();
