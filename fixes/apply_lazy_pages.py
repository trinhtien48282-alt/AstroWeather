"""Build each GUI page on first visit instead of all six at startup. Run from the repo root:  python apply_lazy_pages.py

Why: profile of AstroApp() showed build_ui = 1.5 s of 1.66 s (build_scope 0.51, build_settings 0.43, build_tonight 0.32 ...).
Every edit must match exactly once. If any edit fails, NOTHING is written. Keeps each file's line endings (CRLF or LF).
"""
import os
import sys

E = []  # (path, old, new)


def R(path, old, new):
    E.append((path, old, new))


# gui/app.py: create the empty page frames now, remember each builder, build on first show_page
R("gui/app.py", "        self.pages = {}\n",
  "        self.pages, self.builders, self.built = {}, {}, set()  # a page is built on its first visit: see show_page\n")
R("gui/app.py", "            builder(page)\n            self.pages[key] = page\n",
  "            self.pages[key], self.builders[key] = page, builder\n")
R("gui/app.py", "    def show_page(self, key):\n        self.current = key\n",
  '''    def show_page(self, key):
        if key not in self.built:  # building a page costs hundreds of ms, so only pay it when it is opened
            self.built.add(key)
            self.builders[key](self.pages[key])
            if key == "scope":
                self.update_calcs()
        self.current = key
''')

# gui/calculators_page.py: update_calcs is called at startup and after every analysis, before the page exists
R("gui/calculators_page.py", "    def update_calcs(self):\n        cfg = self.cfg\n",
  '''    def update_calcs(self):
        if "specs" not in self.out:  # Telescope page not built yet: show_page runs this right after building it
            return
        cfg = self.cfg
''')

# gui/settings_page.py: set_location touches planner and forecast widgets that may not exist yet
R("gui/settings_page.py", '''        self.btn_plan.configure(state="normal")
        self.plan_status.configure(text="Local time, format YYYY-MM-DD HH:MM")
        for e in (self.plan_from, self.plan_to):  # old range may be in another timezone
            e.delete(0, "end")
        self.clear_tonight()
        self.hm_labels.delete("all")
        self.hm_data.delete("all")
        self.refresh_plan_list()
        self.show_plan_detail()
        self.draw_alt_graph()
        self.refresh(force=True)
''', '''        if "planner" in self.built:  # these widgets exist only after the page was visited
            self.btn_plan.configure(state="normal")
            self.plan_status.configure(text="Local time, format YYYY-MM-DD HH:MM")
            for e in (self.plan_from, self.plan_to):  # old range may be in another timezone
                e.delete(0, "end")
            self.refresh_plan_list()
            self.show_plan_detail()
            self.draw_alt_graph()
        self.clear_tonight()
        if "forecast" in self.built:
            self.hm_labels.delete("all")
            self.hm_data.delete("all")
        self.refresh(force=True)
''')


def main():
    texts, nl = {}, {}
    for path, old, new in E:
        if path not in texts:
            if not os.path.exists(path):
                sys.exit(f"missing file: {path} (run from the repo root)")
            with open(path, "r", encoding="utf-8", newline="") as f:
                texts[path] = f.read()
            nl[path] = "\r\n" if "\r\n" in texts[path] else "\n"
        o, n = old.replace("\n", nl[path]), new.replace("\n", nl[path])
        c = texts[path].count(o)
        if c != 1:
            sys.exit(f"NOTHING WRITTEN. {path}: expected 1 match, found {c} for:\n{old}")
        texts[path] = texts[path].replace(o, n)
    for path, text in texts.items():
        compile(text, path, "exec")
    for path, text in texts.items():
        with open(path, "w", encoding="utf-8", newline="") as f:
            f.write(text)
    print(f"ok: {len(E)} edits, {len(texts)} files")


main()
