"""Adapt NABH verification to facilities from the application's own snapshot."""
from threading import BoundedSemaphore

from agents.env_config import DEFAULT_ENV_FILE
from agents.verify import SourceError, source_url, verify_facility


def facility_address(row):
    fields = ('address_line1', 'address_line2', 'address_line3', 'address_city',
              'address_stateOrRegion', 'address_zipOrPostcode')
    return ', '.join(dict.fromkeys(str(row.get(field) or '').strip() for field in fields
                                   if str(row.get(field) or '').strip()))


def verification_service(facilities, *, env_file=DEFAULT_ENV_FILE):
    by_id = {row['unique_id']: row for row in facilities}
    slots = BoundedSemaphore(2)

    def verify(payload):
        if not isinstance(payload, dict) or not isinstance(payload.get('facilityId'), str):
            raise ValueError('Provide a facilityId from the search results.')
        row = by_id.get(payload['facilityId'])
        if row is None:
            raise ValueError('Facility not found in the dataset.')
        name = (row.get('name_standardized') or row.get('name') or '').strip()
        address = facility_address(row)
        if len(name) < 2 or len(address) < 5:
            return outcome('unverified', 'Facility name or address is incomplete.')
        if not slots.acquire(blocking=False):
            return outcome('unavailable', 'Verification is busy. Please try again later.')
        try:
            result = verify_facility(name, address, env_file=env_file)
        except Exception:
            return outcome('unavailable', 'Verification could not be completed. Please try again later.')
        finally:
            slots.release()
        urls = []
        if result.get('status') == 'verified':
            for url in result.get('certificate_urls', []):
                try:
                    urls.append(source_url(url))
                except (SourceError, ValueError, TypeError, AttributeError):
                    continue
            if urls:
                return outcome('verified', 'Current branch accreditation is supported by the retrieved evidence.',
                               list(dict.fromkeys(urls)))
        if result.get('status') in {'configuration_error', 'source_unavailable', 'agent_error'}:
            reasons = {
                'configuration_error': 'Verification is not configured on the server.',
                'source_unavailable': 'The official source is currently unavailable. Please try again later.',
                'agent_error': 'The verification agent could not complete its check. Please try again later.',
            }
            return outcome('unavailable', reasons[result['status']])
        return outcome('unverified', 'No trustworthy, current certificate for this facility could be established. '
                       'This does not prove that the facility has no accreditation.')

    return verify


def outcome(status, reason, urls=None):
    return {'status': status,
            'message': 'successfully verified!' if status == 'verified' else "can't be verified",
            'reason': reason, 'certificateUrls': urls or []}
