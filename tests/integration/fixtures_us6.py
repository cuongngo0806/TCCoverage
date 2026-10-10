"""Spec 006 fixtures added on top of the synthetic CMake project of tests/conftest.py."""

SOURCES_FILES = {
    "include/door/conn.h": """#pragma once
struct Session { int id; };
class Conn {
public:
    void on_timer();
    void on_disconnect();
    void on_error();
    void setup();
    void handle_timeout();
    Session* session_ = nullptr;
    int retries_ = 0;
};
void register_cb(void (*cb)(Conn*), Conn* c);
""",
    "src/conn.cpp": """#include "door/conn.h"
static void (*g_cb)(Conn*) = nullptr;
static Conn* g_conn = nullptr;
void register_cb(void (*cb)(Conn*), Conn* c) {
    g_cb = cb;
    g_conn = c;
}
static void timeout_cb(Conn* c) {
    c->handle_timeout();
}
void Conn::handle_timeout() {
    int id = session_->id;
    retries_ += id;
}
void Conn::on_timer() {
    retries_++;
    handle_timeout();
}
void Conn::on_disconnect() {
    handle_timeout();
}
void Conn::on_error() {
    retries_ = 0;
    handle_timeout();
}
void Conn::setup() {
    register_cb(&timeout_cb, this);
}
""",
}


def add_sources_fixture(project):
    project.write(SOURCES_FILES)
    project.edit("CMakeLists.txt", "src/handlers.cpp)", "src/handlers.cpp src/conn.cpp)")
    project.commit("conn")
    project.configure()
