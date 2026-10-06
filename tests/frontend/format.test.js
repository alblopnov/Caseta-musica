const test = require("node:test");
const assert = require("node:assert/strict");
const Format = require("../../static/format.js");

test("formatEta", () => {
  assert.equal(Format.formatEta(0), "menos de 1 min");
  assert.equal(Format.formatEta(59), "menos de 1 min");
  assert.equal(Format.formatEta(60), "~1 min");
  assert.equal(Format.formatEta(150), "~3 min"); // 2.5 rounds up
  assert.equal(Format.formatEta(3569), "~59 min");
  assert.equal(Format.formatEta(3570), "~1 h 00 min"); // rounds to 60 min -> hour form
  assert.equal(Format.formatEta(3599), "~1 h 00 min");
  assert.equal(Format.formatEta(3600), "~1 h 00 min");
  assert.equal(Format.formatEta(3900), "~1 h 05 min");
  assert.equal(Format.formatEta(7200), "~2 h 00 min");
});

test("formatEta handles bad input as zero", () => {
  for (const bad of [NaN, -5, undefined, null, "abc", Infinity]) {
    assert.equal(Format.formatEta(bad), "menos de 1 min", String(bad));
  }
});

test("formatSummary", () => {
  assert.equal(Format.formatSummary(0, 0), "0 canciones en la cola");
  assert.equal(Format.formatSummary(1, 200), "1 canción en la cola | Quedan ~3 min");
  assert.equal(Format.formatSummary(3, 3900), "3 canciones en la cola | Quedan ~1 h 05 min");
  assert.equal(Format.formatSummary(2, 10), "2 canciones en la cola | Quedan menos de 1 min");
});

test("formatClock shows m:ss and h:mm:ss with tabular-friendly padding", () => {
  assert.equal(Format.formatClock(0), "0:00");
  assert.equal(Format.formatClock(5), "0:05");
  assert.equal(Format.formatClock(65), "1:05");
  assert.equal(Format.formatClock(83.9), "1:23"); // floors, never rounds up past the song
  assert.equal(Format.formatClock(3599), "59:59");
  assert.equal(Format.formatClock(3600), "1:00:00");
  assert.equal(Format.formatClock(3725), "1:02:05");
  assert.equal(Format.formatClock(NaN), "0:00");
  assert.equal(Format.formatClock(-4), "0:00");
  assert.equal(Format.formatClock(undefined), "0:00");
});
