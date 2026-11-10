# Accessibility Conformance

This repository conforms to **WCAG 2.2 Level AA**.

## Conformance & Design Considerations

- **Text Alternatives (WCAG 1.1.1):** Profile README images include descriptive alt text and complete textual alternatives for all information, data points, and links.
- **Images of Text (WCAG 1.4.5):** All technical skills, biographical summaries, and links are duplicated in semantic Markdown text so no information is locked in raster or vector imagery alone.
- **Contrast (WCAG 1.4.3):** Vector badge and readout text styles maintain a minimum contrast ratio of 4.5:1 against card backgrounds in both light and dark themes.
- **Reduced Motion (WCAG 2.2.2 / 2.3.3):** Embedded vector CSS animations honor `prefers-reduced-motion: reduce` by disabling star twinkle, rocket drift, flame flicker, and shooting star effects.
- **Headings & Structure (WCAG 1.3.1 / 2.4.6):** Semantic Markdown headings (`#`, `##`) establish a logical, screen-reader friendly heading hierarchy.
- **Meaningful Link Text (WCAG 2.4.4):** Links use clear anchor text describing the destination rather than bare or ambiguous labels.

## Reporting Barriers

If you encounter any accessibility barrier on this profile, please open an issue or email [karthik.subramanian@berkeley.edu](mailto:karthik.subramanian@berkeley.edu).
