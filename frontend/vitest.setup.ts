import "@testing-library/jest-dom/vitest";

if (!HTMLElement.prototype.scrollIntoView) {
	Object.defineProperty(HTMLElement.prototype, "scrollIntoView", {
		value: () => {},
		writable: true,
	});
}
