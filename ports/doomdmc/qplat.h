#pragma once
#include <stdint.h>
#include "qos.h"
extern const qos_api *qapi;
void q_putc(int c);
void q_puts(const char *s);
void q_putu(uint32_t v);
void q_puthex(uint32_t v);
extern uint32_t q_dump_req, q_keys;
extern uint32_t q_nor_base;
extern int q_ep_pending;
int q_ep_probe(void);
void q_ep_slot(int ep);
void q_ep_set(int cur, int n);
int dmc_cur_episode(void);
