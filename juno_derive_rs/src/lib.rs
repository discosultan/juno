use proc_macro::TokenStream;
use quote::quote;
use syn::{parse_macro_input, ItemStruct};

#[proc_macro_derive(Chromosome)]
pub fn derive_chromosome(input: TokenStream) -> TokenStream {
    let input = parse_macro_input!(input as ItemStruct);

    let name = &input.ident;
    let (impl_generics, ty_generics, where_clause) = input.generics.split_for_impl();

    let len_field_count = input.fields.iter().count();

    let generate_field_name = input.fields.iter().map(|field| &field.ident);

    let cross_field_index = 0..len_field_count;
    let cross_field_name = generate_field_name.clone();

    let mutate_field_index = cross_field_index.clone();
    let mutate_field_name = generate_field_name.clone();

    let output = quote! {
        impl #impl_generics Chromosome for #name #ty_generics #where_clause {
            fn len() -> usize {
                #len_field_count
            }

            fn generate(rng: &mut StdRng) -> Self {
                Self {
                    #(
                        #generate_field_name: #generate_field_name(rng),
                    )*
                }
            }

            fn cross(&mut self, other: &mut Self, i: usize) {
                match i {
                    #(
                        #cross_field_index => std::mem::swap(
                            &mut self.#cross_field_name,
                            &mut other.#cross_field_name,
                        ),
                    )*
                    _ => panic!("index out of bounds"),
                };
            }

            fn mutate(&mut self, rng: &mut StdRng, i: usize) {
                match i {
                    #(
                        #mutate_field_index => self.#mutate_field_name = #mutate_field_name(rng),
                    )*
                    _ => panic!("index out of bounds"),
                };
            }
        }
    };

    TokenStream::from(output)
}

#[proc_macro_derive(Signal)]
pub fn derive_signal(input: TokenStream) -> TokenStream {
    let input = parse_macro_input!(input as ItemStruct);

    let name = &input.ident;
    let (impl_generics, ty_generics, where_clause) = input.generics.split_for_impl();

    let output = quote! {
        impl #impl_generics Signal for #name #ty_generics #where_clause {
            fn advice(&self) -> crate::Advice {
                self.advice
            }
        }
    };

    TokenStream::from(output)
}
