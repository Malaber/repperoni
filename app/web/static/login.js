import {initFastPasskey} from "/api/v1/auth/assets/fastpasskey.js";


const bootstrapToken = document.querySelector("[data-registration-bootstrap-token]");
if (bootstrapToken) {
  const nativeFetch = globalThis.fetch.bind(globalThis);
  globalThis.fetch = (input, init = {}) => {
    const url = new URL(typeof input === "string" ? input : input.url, globalThis.location.href);
    if (
      url.pathname === "/api/v1/auth/register/options"
      || url.pathname === "/api/v1/auth/register/verify"
    ) {
      const headers = new Headers(init.headers);
      headers.set("X-Repperoni-Registration-Token", bootstrapToken.value);
      return nativeFetch(input, {...init, headers});
    }
    return nativeFetch(input, init);
  };
}

initFastPasskey({translate: (_key, _values, fallback) => fallback});
