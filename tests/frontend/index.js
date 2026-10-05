// Node 22 treats `node --test tests/frontend/` as a module path instead of
// scanning the directory, so this entry point loads every test file.
require("./format.test.js");
require("./common.test.js");
require("./userlogic.test.js");
require("./adminlogic.test.js");
