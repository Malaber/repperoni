import {initFastPasskey} from "/api/v1/auth/assets/fastpasskey.js";


initFastPasskey({translate: (_key, _values, fallback) => fallback});
