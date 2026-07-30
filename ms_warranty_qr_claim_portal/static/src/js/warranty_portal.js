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
        'change input[name="delivery_method"]': '_onDeliveryMethodChange', 
    },

    start: function () {
        console.log("========== ODOO WIDGET BOUND ==========");
        this._handleDeliveryLocationVisibility();
        return this._super(...arguments);
    },

    _onServiceCenterChange: function (ev) {
        fetchCenterAddress(ev.currentTarget.value, this.el);
    },

    _onDeliveryMethodChange: function () {
        this._handleDeliveryLocationVisibility();
    },

   
    _handleDeliveryLocationVisibility: function () {
        const selectedMethod = this.$('input[name="delivery_method"]:checked').val();
        const $locationDiv = this.$('#customer_location_div');
        const $locationInput = this.$('#customer_location');

        if (selectedMethod === 'courier') {
         
            $locationDiv.removeClass('d-none').hide().slideDown(200);
            $locationInput.attr('required', 'required');
        } else {
          
            $locationDiv.slideUp(200, function() {
                $locationDiv.addClass('d-none');
            });
            $locationInput.removeAttr('required');
            $locationInput.val(''); 
        }
    }
});