"""Spec 009 fixture: state written in one place and read in another (neither caller nor callee)."""

STATE_FILES = {
    "include/door/store.h": """#pragma once
#include <mutex>
#include <vector>
struct StoreOptions {
    int max_items = 16;
};
class Store {
public:
    explicit Store(const StoreOptions& o);
    void add(int v);
    int get(int i) const;
    void schedule();
    void background();
    int pending() const;
    void SetCount(int n);
    int Count() const;
    void append(int v);
    int snapshot();
    void release();
private:
    StoreOptions opts_;
    std::vector<int> items_;
    bool scheduled_ = false;
    int count_ = 0;
    std::mutex mu_;
    int snaps_ = 0;
};
int store_user(Store& s);
int capacity_user(const StoreOptions& o);
""",
    "src/store.cpp": """#include "door/store.h"
Store::Store(const StoreOptions& o) : opts_(o), scheduled_(false) {}
void Store::add(int v) {
    if (static_cast<int>(items_.size()) < opts_.max_items) {
        items_.push_back(v * 2);
    }
}
int Store::get(int i) const {
    return items_[i] / 2;
}
void Store::schedule() {
    if (!scheduled_) {
        scheduled_ = true;
        background();
    }
}
void Store::background() {
    if (scheduled_) {
        items_.clear();
    }
}
int Store::pending() const {
    return scheduled_ ? 1 : 0;
}
void Store::SetCount(int n) { count_ = n; }
int Store::Count() const { return count_; }
void Store::append(int v) {
    SetCount(Count() + 1);
    items_.push_back(v);
}
int Store::snapshot() {
    std::lock_guard<std::mutex> g(mu_);
    snaps_ += 1;
    return snaps_;
}
void Store::release() {
    std::lock_guard<std::mutex> g(mu_);
    snaps_ -= 1;
}
int store_user(Store& s) {
    if (s.Count() != 3) {
        return -1;
    }
    return s.get(0);
}
int capacity_user(const StoreOptions& o) {
    return o.max_items * 2;
}
""",
}


def add_state_fixture(project):
    project.write(STATE_FILES)
    project.edit("CMakeLists.txt", "src/handlers.cpp)", "src/handlers.cpp src/store.cpp)")
    project.commit("store")
    project.configure()
