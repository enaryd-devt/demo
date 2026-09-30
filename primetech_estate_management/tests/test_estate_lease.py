from odoo.tests.common import TransactionCase
from odoo.exceptions import ValidationError


class TestEstateLease(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.property = cls.env['estate.property'].create({'name': 'Immeuble test', 'property_type_id': cls.env.ref('primetech_estate_management.property_type_building').id})
        cls.unit = cls.env['estate.unit'].create({'name': 'A01', 'property_id': cls.property.id, 'unit_type_id': cls.env.ref('primetech_estate_management.unit_type_apartment').id, 'indicative_rent': 100000})
        cls.tenant = cls.env['res.partner'].create({'name': 'Locataire test', 'is_estate_tenant': True})

    def _lease_vals(self):
        return {'tenant_id': self.tenant.id, 'property_id': self.property.id, 'unit_id': self.unit.id, 'date_start': '2026-01-01', 'date_end': '2026-12-31', 'rent_amount': 100000}

    def test_activation_occupies_unit_and_generates_schedule(self):
        lease = self.env['estate.lease'].create(self._lease_vals())
        lease.action_activate()
        self.assertEqual(lease.state, 'active')
        self.assertEqual(self.unit.state, 'occupied')
        self.assertTrue(lease.schedule_ids)

    def test_overlapping_leases_are_forbidden(self):
        lease = self.env['estate.lease'].create(self._lease_vals())
        lease.action_activate()
        conflicting = self.env['estate.lease'].create(self._lease_vals())
        with self.assertRaises(ValidationError):
            conflicting.action_activate()
