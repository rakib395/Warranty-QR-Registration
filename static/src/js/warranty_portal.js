/** @odoo-module */

import publicWidget from "@web/legacy/js/public/public_widget";
import { rpc } from "@web/core/network/rpc";


async function fetchCenterAddress(centerId, el) {
    console.log("Fetching address for Center ID:", centerId);
    
    const container = el.querySelector('#service_center_address_container');
    const addressBox = el.querySelector('#service_center_full_address');

    if (!container || !addressBox) {
        console.error("Address elements not found in DOM");
        return;
    }

    if (!centerId) {
        container.style.display = 'none';
        addressBox.innerText = '';
        return;
    }

    try {
        const result = await rpc('/warranty/get_center_address', {
            center_id: parseInt(centerId),
        });

        console.log("Backend RPC Result:", result);

        if (result && result.status === 'success') {
            addressBox.innerText = result.address;
            container.style.display = 'block';
        } else {
            addressBox.innerText = 'Address not found.';
            container.style.display = 'block';
        }
    } catch (error) {
        console.error("RPC Error fetching address:", error);
        addressBox.innerText = 'Error loading address.';
        container.style.display = 'block';
    }
}

publicWidget.registry.WarrantyPortalAddress = publicWidget.Widget.extend({
    selector: '.o_warranty_claim_portal_form', 
    events: {
        'change select[name="portal_service_center_id"]': '_onServiceCenterChange',
    },

    start: function () {
        console.log("========== ODOO OWL/LEGACY WIDGET BOUND ==========");
        return this._super(...arguments);
    },

    _onServiceCenterChange: function (ev) {
        fetchCenterAddress(ev.currentTarget.value, this.el);
    },
});


document.addEventListener('DOMContentLoaded', () => {
    console.log("========== DOM READY BACKUP RUNNING ==========");
    const selectEl = document.querySelector('select[name="portal_service_center_id"]');
    if (selectEl) {
        selectEl.addEventListener('change', (e) => {
            fetchCenterAddress(e.target.value, document);
        });
    }
});