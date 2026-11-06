static uint32_t divlu_dummy;
// floor((u1 * 2^32 + u0) / v) for u1 < v: Hacker's Delight divlu, three hardware divides.
static uint32_t divlu(uint32_t u1, uint32_t u0, uint32_t v)
{
    uint32_t s = 0, t = v;
    if (t < 0x10000u) { s += 16; t <<= 16; }
    if (t < 0x1000000u) { s += 8; t <<= 8; }
    if (t < 0x10000000u) { s += 4; t <<= 4; }
    if (t < 0x40000000u) { s += 2; t <<= 2; }
    if (t < 0x80000000u) { s += 1; t <<= 1; }
    v = t;
    uint32_t vn1 = v >> 16, vn0 = v & 0xFFFFu;
    uint32_t un32 = s ? (u1 << s) | (u0 >> (32 - s)) : u1;
    uint32_t un10 = u0 << s;
    uint32_t un1 = un10 >> 16, un0 = un10 & 0xFFFFu;
    uint32_t q1 = un32 / vn1, rhat = un32 - q1 * vn1;
    while (q1 >= 0x10000u || q1 * vn0 > ((rhat << 16) | un1))
    {
	q1--;
	rhat += vn1;
	if (rhat >= 0x10000u)
	    break;
    }
    uint32_t un21 = (un32 << 16) + un1 - q1 * v;
    uint32_t q0 = un21 / vn1;
    rhat = un21 - q0 * vn1;
    while (q0 >= 0x10000u || q0 * vn0 > ((rhat << 16) | un0))
    {
	q0--;
	rhat += vn1;
	if (rhat >= 0x10000u)
	    break;
    }
    return (q1 << 16) + q0;
}

fixed_t FixedDiv(fixed_t a, fixed_t b)
{
    if ((abs(a) >> 14) >= abs(b))
    {
	return (a^b) < 0 ? INT_MIN : INT_MAX;
    }
    else
    {
	uint32_t ua = a < 0 ? 0u - (uint32_t) a : (uint32_t) a;
	uint32_t ub = b < 0 ? 0u - (uint32_t) b : (uint32_t) b;
	uint32_t q;

	if ((ua >> 14) >= ub)
	    q = UDivFix(ua, ub);	// only a == INT_MIN gets here
	else if (ua < 0x10000u)
	    q = (ua << 16) / ub;
	else if (ub < 0x10000u)
	{
	    uint32_t q1 = ua / ub, r = ua - q1 * ub;
	    q = (q1 << 16) + ((r << 16) / ub);
	}
	else
	    q = divlu(ua >> 16, ua << 16, ub);

	return (fixed_t) ((a^b) < 0 ? 0u - q : q);
    }
}
