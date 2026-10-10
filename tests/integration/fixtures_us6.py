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


FLOW_FILES = {
    "include/door/frame.h": """#pragma once
#include <deque>
struct Frame { int code; int len; };
void transport_send(const char* buf, int len);
class Producer {
public:
    Frame build_status(int raw);
    void tick(int raw);
    int base_ = 1;
};
class Relay {
public:
    void relay(const Frame& f);
    std::deque<Frame> q_;
};
class Publisher {
public:
    void publish(const Frame& f);
};
""",
    "src/frame.cpp": """#include "door/frame.h"
Frame Producer::build_status(int raw) {
    Frame f;
    f.code = raw * 2;
    f.len = 4;
    return f;
}
void Producer::tick(int raw) {
    Frame f = build_status(raw);
    Relay r;
    r.relay(f);
}
void Relay::relay(const Frame& f) {
    Frame copy = f;
    Publisher p;
    p.publish(copy);
}
void Publisher::publish(const Frame& f) {
    transport_send(reinterpret_cast<const char*>(&f), f.len);
}
""",
}


def add_flow_fixture(project):
    project.write(FLOW_FILES)
    project.edit("CMakeLists.txt", "src/handlers.cpp)", "src/handlers.cpp src/frame.cpp)")
    project.commit("frame")
    project.configure()


PATTERN_FILES = {
    "include/door/codec.h": """#pragma once
enum class State { Idle, Busy };
int encode_frame(int v);
int decode_frame(int w);
int checksum_legacy(const int* data, int n);
int checksum_fast(const int* data, int n);
const char* state_name(State s);
int parse_code(int raw);
int use_parse(int raw);
struct Cfg { bool fast_mode_enabled = false; };
extern Cfg g_cfg;
int run_a(int x);
int run_b(int x);
struct Counter {
    int count_ = 0;
    void bump();
    int read() const;
};
int process(int* buf);
""",
    "src/codec.cpp": """#include "door/codec.h"
Cfg g_cfg;
int encode_frame(int v) {
    return v * 2 + 1;
}
int decode_frame(int w) {
    return (w - 1) / 2;
}
int checksum_legacy(const int* data, int n) {
    int sum = 0;
    for (int i = 0; i < n; ++i) sum = (sum + data[i] * 31) % 65521;
    return sum;
}
int checksum_fast(const int* data, int n) {
    int sum = 0;
    for (int i = 0; i < n; ++i) sum = (sum + data[i] * 31) % 65521;
    return sum;
}
const char* state_name(State s) {
    switch (s) {
    case State::Idle: return "idle";
    case State::Busy: return "busy";
    }
    return "?";
}
int parse_code(int raw) {
    if (raw < 0)
        return -1;
    return raw;
}
int use_parse(int raw) {
    int r = parse_code(raw);
    if (r < 0)
        return 0;
    return r;
}
int run_a(int x) {
    return x;
}
int run_b(int x) {
    if (g_cfg.fast_mode_enabled)
        return x * 2;
    return x;
}
void Counter::bump() {
    count_ += 1;
}
int Counter::read() const {
    return count_;
}
int process(int* buf) {
    int* p = new int[4];
    p[0] = buf[0];
    int r = p[0];
    delete[] p;
    return r;
}
""",
}


def add_pattern_fixture(project):
    project.write(PATTERN_FILES)
    project.edit("CMakeLists.txt", "src/handlers.cpp)", "src/handlers.cpp src/codec.cpp)")
    project.commit("codec")
    project.configure()
