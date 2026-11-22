"""Snapshot-bound Practo lookup with an expiring cache and single-flight requests."""
from collections import OrderedDict
from concurrent.futures import Future, TimeoutError
from threading import BoundedSemaphore, Lock
from time import monotonic

from agents.practo import PractoAgent, report


def practo_rating_service(facilities, *, agent=None, clock=monotonic):
    by_id = {row['unique_id']: row for row in facilities}
    agent = agent or PractoAgent()
    cache, pending = OrderedDict(), {}
    lock = Lock()
    slots = BoundedSemaphore(2)

    def lookup(payload):
        if not isinstance(payload, dict) or not isinstance(payload.get('facilityId'), str):
            raise ValueError('Provide a facilityId from the search results.')
        facility_id = payload['facilityId']
        if facility_id not in by_id:
            raise ValueError('Facility not found in the dataset.')
        with lock:
            cached = cache.get(facility_id)
            if cached and cached[0] > clock():
                cache.move_to_end(facility_id)
                return dict(cached[1])
            existing = pending.get(facility_id)
            if existing is None:
                if not slots.acquire(blocking=False):
                    return report('unavailable', 'Practo lookup is busy. Please try again later.')
                pending[facility_id] = Future()
            future = pending[facility_id]
        if existing is not None:
            try:
                return dict(future.result(timeout=180))
            except TimeoutError:
                return report('unavailable', 'Practo lookup is still running. Please try again later.')
        try:
            try:
                result = agent.lookup(by_id[facility_id])
            except Exception:
                result = report('unavailable', 'Practo lookup could not be completed.')
            with lock:
                ttl = 21600 if result['status'] == 'available' else 300
                cache[facility_id] = (clock() + ttl, result)
                cache.move_to_end(facility_id)
                while len(cache) > 256:
                    cache.popitem(last=False)
                pending.pop(facility_id)
                future.set_result(result)
            return dict(result)
        finally:
            slots.release()

    return lookup
